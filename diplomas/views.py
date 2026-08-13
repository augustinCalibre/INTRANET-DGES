import csv
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.permissions import (
    can_access_diplomas,
    can_manage_diplomas,
    can_transmit_to_dg,
    can_validate_as_dg,
    is_admin_user,
)
from core.utils import log_activity, paginate, querystring_without, safe_next_url

from .forms import DiplomeForm, LotDiplomesForm
from .models import Diplome, LotDiplomes
from .selectors import (
    get_diploma_status_counts,
    get_lot_status_counts,
    get_visible_diplomas,
    get_visible_lots,
)
from .services import (
    register_diploma_history,
    register_lot_history,
)
from .workflow import apply_transition, get_available_transitions

LOTS_PER_PAGE = 25
DIPLOMAS_PER_PAGE = 20
SEARCH_RESULTS_PER_PAGE = 25


def _require_management(user):
    """Modification du contenu d'un lot : reservee a l'agent d'etude."""
    if not can_manage_diplomas(user):
        raise PermissionDenied


def _require_access(user):
    """Consultation et export : agent d'etude, Secretariat, DG."""
    if not can_access_diplomas(user):
        raise PermissionDenied


def _get_lot_for_management(request, pk):
    _require_management(request.user)
    return get_object_or_404(get_visible_lots(request.user), pk=pk)


def _get_lot_for_workflow(request, pk):
    """Le controle fin releve du circuit : chaque etape verifie sa capacite."""
    _require_access(request.user)
    return get_object_or_404(get_visible_lots(request.user), pk=pk)


def _filter_lots(request, lots):
    status_filter = request.GET.get("statut", "").strip()
    search_term = request.GET.get("q", "").strip()
    anomaly_filter = request.GET.get("anomalies", "").strip()
    period_filter = request.GET.get("periode", "").strip()
    active_filter_label = ""

    if status_filter:
        lots = lots.filter(statut=status_filter)
        try:
            active_filter_label = LotDiplomes.Status(status_filter).label
        except ValueError:
            active_filter_label = ""

    if anomaly_filter == "1":
        lots = lots.filter(nb_anomalies__gt=0)
        active_filter_label = "Lots présentant des anomalies"

    if period_filter == "month":
        today = timezone.localdate()
        lots = lots.filter(date_arrivee__year=today.year, date_arrivee__month=today.month)
        active_filter_label = active_filter_label or "Lots du mois en cours"

    if search_term:
        lots = lots.filter(
            Q(reference__icontains=search_term)
            | Q(etablissement__icontains=search_term)
            | Q(observation__icontains=search_term)
            | Q(diplomes__nom_beneficiaire__icontains=search_term)
            | Q(diplomes__numero_diplome__icontains=search_term)
        ).distinct()

    return lots, {
        "status_filter": status_filter,
        "search_term": search_term,
        "anomaly_filter": anomaly_filter,
        "period_filter": period_filter,
        "active_filter_label": active_filter_label,
    }


@login_required
def lot_list(request):
    lots, filters = _filter_lots(request, get_visible_lots(request.user))
    page = paginate(request, lots, LOTS_PER_PAGE)

    context = {
        "page_obj": page,
        "lots": page.object_list,
        "status_counts": get_lot_status_counts(request.user),
        "status_choices": LotDiplomes.Status.choices,
        "can_manage": can_manage_diplomas(request.user),
        "can_transmit": can_transmit_to_dg(request.user),
        "can_sign": can_validate_as_dg(request.user),
        "can_export": can_access_diplomas(request.user),
        "can_delete": is_admin_user(request.user),
        "base_querystring": querystring_without(request, "page"),
        "total_lots": page.paginator.count,
        **filters,
    }
    return render(request, "diplomas/lot_list.html", context)


@login_required
def lot_create(request):
    _require_management(request.user)

    if request.method == "POST":
        form = LotDiplomesForm(request.POST)
        if form.is_valid():
            lot = form.save(commit=False)
            lot.cree_par = request.user
            if not lot.agent_receptionnaire:
                lot.agent_receptionnaire = request.user
            lot.save()
            register_lot_history(lot, request.user, "Réception du lot", "", lot.statut)
            log_activity(request.user, "Réception d'un lot de diplômes", "Diplômes", lot.reference)
            messages.success(
                request,
                f"Le lot {lot.reference} a été enregistré. Ajoutez maintenant les diplômes reçus.",
            )
            return redirect("diplomas:lot_detail", pk=lot.pk)
    else:
        initial = {"date_arrivee": timezone.localdate()}
        profile = getattr(request.user, "profil", None)
        if profile and profile.service_id:
            initial["service_concerne"] = profile.service
        form = LotDiplomesForm(initial=initial)

    return render(
        request,
        "diplomas/lot_form.html",
        {
            "form": form,
            "title": "Enregistrer un lot d'arrivée",
            "is_creation": True,
        },
    )


@login_required
def lot_edit(request, pk):
    lot = _get_lot_for_management(request, pk)

    if request.method == "POST":
        form = LotDiplomesForm(request.POST, instance=lot)
        if form.is_valid():
            lot = form.save()
            register_lot_history(lot, request.user, "Mise à jour de la fiche du lot", lot.statut, lot.statut)
            log_activity(request.user, "Mise à jour d'un lot de diplômes", "Diplômes", lot.reference)
            messages.success(request, "La fiche du lot a été mise à jour.")
            return redirect("diplomas:lot_detail", pk=lot.pk)
    else:
        form = LotDiplomesForm(instance=lot)

    return render(
        request,
        "diplomas/lot_form.html",
        {
            "form": form,
            "title": f"Modifier {lot.reference}",
            "lot": lot,
            "is_creation": False,
        },
    )


@login_required
def lot_detail(request, pk):
    lot = get_object_or_404(get_visible_lots(request.user), pk=pk)

    status_filter = request.GET.get("dstatut", "").strip()
    search_term = request.GET.get("dq", "").strip()
    diplomas = lot.diplomes.all()

    if status_filter:
        diplomas = diplomas.filter(statut=status_filter)
    if search_term:
        diplomas = diplomas.filter(
            Q(nom_beneficiaire__icontains=search_term)
            | Q(numero_diplome__icontains=search_term)
            | Q(filiere__icontains=search_term)
        )

    page = paginate(request, diplomas, DIPLOMAS_PER_PAGE)
    steps = [
        {
            "key": status,
            "label": LotDiplomes.Status(status).label,
            "index": index + 1,
            "is_done": bool(lot.etape_index) and index + 1 < lot.etape_index,
            "is_current": index + 1 == lot.etape_index,
        }
        for index, status in enumerate(LotDiplomes.STATUS_FLOW)
    ]

    context = {
        "lot": lot,
        "steps": steps,
        "page_obj": page,
        "diplomas": page.object_list,
        "diploma_status_choices": Diplome.Status.choices,
        "dstatut": status_filter,
        "dq": search_term,
        "transitions": get_available_transitions(lot, request.user),
        "histories": lot.historiques.select_related("utilisateur")[:20],
        "can_manage": can_manage_diplomas(request.user),
        "can_delete": is_admin_user(request.user),
        "anomaly_choices": Diplome.Anomalie.choices,
        "base_querystring": querystring_without(request, "page"),
    }
    return render(request, "diplomas/lot_detail.html", context)


@login_required
@require_POST
def lot_status(request, pk, statut):
    lot = _get_lot_for_workflow(request, pk)
    commentaire = request.POST.get("commentaire", "")

    succeeded, message = apply_transition(lot, statut, request.user, commentaire)
    if succeeded:
        messages.success(request, message)
        log_activity(
            request.user,
            f"Lot de diplômes : {message}",
            "Diplômes",
            lot.reference,
        )
    else:
        messages.error(request, message)

    return redirect(safe_next_url(request, request.POST.get("next"), "diplomas:lot_list"))


@login_required
@require_POST
def lot_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    lot = get_object_or_404(LotDiplomes, pk=pk)
    reference = lot.reference
    lot.delete()
    log_activity(request.user, "Suppression d'un lot de diplômes", "Diplômes", reference)
    messages.success(request, f"Le lot {reference} et ses diplômes ont été supprimés.")
    return redirect(safe_next_url(request, request.POST.get("next"), "diplomas:lot_list"))


# ------------------------------------------------------------------ diplomes


@login_required
def diploma_create(request, lot_pk):
    lot = _get_lot_for_management(request, lot_pk)
    if not lot.allows_diploma_edition:
        messages.error(
            request,
            "Ce lot est déjà transmis à la signature : son contenu ne peut plus être modifié.",
        )
        return redirect("diplomas:lot_detail", pk=lot.pk)

    save_and_continue = False
    if request.method == "POST":
        form = DiplomeForm(request.POST, lot=lot)
        save_and_continue = "save_and_add" in request.POST
        if form.is_valid():
            diplome = form.save(commit=False)
            diplome.lot = lot
            diplome.save()
            register_diploma_history(diplome, request.user, "Enregistrement du diplôme", "", diplome.statut)
            log_activity(request.user, "Ajout d'un diplôme", "Diplômes", f"{lot.reference} / {diplome.numero_diplome}")
            messages.success(request, f"Le diplôme de {diplome.nom_beneficiaire} a été enregistré.")
            if save_and_continue:
                return redirect("diplomas:diploma_create", lot_pk=lot.pk)
            return redirect("diplomas:lot_detail", pk=lot.pk)
    else:
        form = DiplomeForm(lot=lot, initial={"annee_academique": ""})

    return render(
        request,
        "diplomas/diploma_form.html",
        {
            "form": form,
            "lot": lot,
            "title": "Ajouter un diplôme",
            "is_creation": True,
        },
    )


@login_required
def diploma_detail(request, pk):
    diplome = get_object_or_404(
        get_visible_diplomas(request.user).select_related("lot", "lot__agent_receptionnaire"),
        pk=pk,
    )
    return render(
        request,
        "diplomas/diploma_detail.html",
        {
            "diplome": diplome,
            "lot": diplome.lot,
            "histories": diplome.historiques.select_related("utilisateur")[:30],
            "can_manage": can_manage_diplomas(request.user),
            "can_delete": is_admin_user(request.user),
        },
    )


@login_required
def diploma_edit(request, pk):
    _require_management(request.user)
    diplome = get_object_or_404(get_visible_diplomas(request.user), pk=pk)
    lot = diplome.lot

    if not lot.allows_diploma_edition:
        messages.error(
            request,
            "Ce lot est transmis à la signature : utilisez l'action de retrait pour tracer une remise.",
        )
        return redirect("diplomas:diploma_detail", pk=diplome.pk)

    previous_status = diplome.statut
    if request.method == "POST":
        form = DiplomeForm(request.POST, instance=diplome, lot=lot)
        if form.is_valid():
            diplome = form.save()
            action = "Mise à jour du diplôme"
            if previous_status != diplome.statut:
                action = f"Changement de statut : {Diplome.Status(diplome.statut).label}"
            register_diploma_history(
                diplome,
                request.user,
                action,
                previous_status,
                diplome.statut,
                commentaire=diplome.get_anomalie_display() if diplome.anomalie else "",
            )
            log_activity(
                request.user,
                "Mise à jour d'un diplôme",
                "Diplômes",
                f"{lot.reference} / {diplome.numero_diplome}",
            )
            messages.success(request, "Le diplôme a été mis à jour.")
            return redirect("diplomas:lot_detail", pk=lot.pk)
    else:
        form = DiplomeForm(instance=diplome, lot=lot)

    return render(
        request,
        "diplomas/diploma_form.html",
        {
            "form": form,
            "lot": lot,
            "diplome": diplome,
            "title": f"Modifier {diplome.nom_beneficiaire}",
            "is_creation": False,
            "histories": diplome.historiques.select_related("utilisateur")[:10],
        },
    )


@login_required
@require_POST
def diploma_mark_compliant(request, pk):
    _require_management(request.user)
    diplome = get_object_or_404(get_visible_diplomas(request.user), pk=pk)

    if not diplome.lot.allows_diploma_edition:
        messages.error(request, "Ce lot est déjà transmis à la signature.")
        return redirect(safe_next_url(request, request.POST.get("next"), "diplomas:lot_list"))

    if diplome.statut == Diplome.Status.CONFORME:
        messages.info(request, "Ce diplôme est déjà marqué conforme.")
        return redirect(safe_next_url(request, request.POST.get("next"), "diplomas:lot_list"))

    previous_status = diplome.statut
    diplome.statut = Diplome.Status.CONFORME
    diplome.anomalie = ""
    diplome.save(update_fields=["statut", "anomalie", "updated_at"])
    register_diploma_history(diplome, request.user, "Diplôme déclaré conforme", previous_status, diplome.statut)
    messages.success(request, f"{diplome.nom_beneficiaire} : diplôme déclaré conforme.")
    return redirect(safe_next_url(request, request.POST.get("next"), "diplomas:lot_list"))


@login_required
@require_POST
def diploma_withdraw(request, pk):
    _require_management(request.user)
    diplome = get_object_or_404(get_visible_diplomas(request.user), pk=pk)

    if not diplome.lot.allows_withdrawal:
        messages.error(request, "Le retrait ne peut être tracé qu'après signature du lot.")
        return redirect(safe_next_url(request, request.POST.get("next"), "diplomas:lot_list"))

    if diplome.statut == Diplome.Status.RETIRE:
        messages.info(request, "Ce diplôme est déjà marqué comme retiré.")
        return redirect(safe_next_url(request, request.POST.get("next"), "diplomas:lot_list"))

    beneficiaire = request.POST.get("retire_par", "").strip()
    previous_status = diplome.statut
    diplome.statut = Diplome.Status.RETIRE
    diplome.date_retrait = timezone.now()
    diplome.retire_par = beneficiaire[:180]
    diplome.save(update_fields=["statut", "date_retrait", "retire_par", "updated_at"])
    register_diploma_history(
        diplome,
        request.user,
        "Retrait du diplôme",
        previous_status,
        diplome.statut,
        commentaire=f"Retiré par {beneficiaire}." if beneficiaire else "",
    )
    log_activity(
        request.user,
        "Retrait d'un diplôme",
        "Diplômes",
        f"{diplome.lot.reference} / {diplome.numero_diplome}",
    )
    messages.success(request, f"Le retrait du diplôme de {diplome.nom_beneficiaire} a été enregistré.")
    return redirect(safe_next_url(request, request.POST.get("next"), "diplomas:lot_list"))


@login_required
@require_POST
def diploma_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    diplome = get_object_or_404(Diplome, pk=pk)
    label = f"{diplome.lot.reference} / {diplome.numero_diplome}"
    diplome.delete()
    log_activity(request.user, "Suppression d'un diplôme", "Diplômes", label)
    messages.success(request, "Le diplôme a été supprimé du lot.")
    return redirect(safe_next_url(request, request.POST.get("next"), "diplomas:lot_list"))


# ------------------------------------------------------- liste du lot


@login_required
def lot_liste_download(request, pk):
    """Sert la liste des diplômes remise avec le lot.

    La pièce n'est jamais servie en direct depuis le dossier des médias :
    elle passe par cette vue, qui vérifie d'abord que le compte a le droit de
    voir ce lot.

    Avec `?consulter=1`, un PDF s'ouvre dans la page au lieu d'être téléchargé.
    C'est l'usage courant : on regarde la liste pendant qu'on relève les
    diplômes non conformes, on ne l'archive pas sur son poste.

    Seul le PDF est affiché ainsi. Un document Word est toujours téléchargé :
    le navigateur ne sait pas le rendre, et le servir en ligne reviendrait à
    laisser un fichier déposé décider de la façon dont il est interprété.
    """
    lot = _get_lot_for_workflow(request, pk)
    if not lot.fichier_liste:
        raise Http404("Aucune liste n'est jointe à ce lot.")

    nom = Path(lot.fichier_liste.name).name
    est_pdf = nom.lower().endswith(".pdf")
    consulter = request.GET.get("consulter") == "1" and est_pdf

    if not consulter:
        log_activity(
            request.user, "Téléchargement de la liste d'un lot", "Diplômes", lot.reference
        )

    reponse = FileResponse(
        lot.fichier_liste.open("rb"),
        as_attachment=not consulter,
        filename=nom,
        content_type="application/pdf" if est_pdf else None,
    )
    # Le navigateur doit s'en tenir au type annonce et ne pas le deviner a
    # partir du contenu : c'est ce qui empeche un fichier depose de se faire
    # passer pour autre chose.
    reponse["X-Content-Type-Options"] = "nosniff"
    return reponse


# ---------------------------------------------------- recherche et exports


@login_required
def diploma_search(request):
    search_term = request.GET.get("q", "").strip()
    status_filter = request.GET.get("statut", "").strip()
    year_filter = request.GET.get("annee", "").strip()
    results = None
    page = None

    if search_term or status_filter or year_filter:
        results = get_visible_diplomas(request.user).select_related("lot")
        if search_term:
            results = results.filter(
                Q(nom_beneficiaire__icontains=search_term)
                | Q(numero_diplome__icontains=search_term)
                | Q(filiere__icontains=search_term)
                | Q(etablissement__icontains=search_term)
                | Q(lot__etablissement__icontains=search_term)
                | Q(lot__reference__icontains=search_term)
            )
        if status_filter:
            results = results.filter(statut=status_filter)
        if year_filter:
            results = results.filter(annee_academique__icontains=year_filter)
        page = paginate(request, results.order_by("nom_beneficiaire"), SEARCH_RESULTS_PER_PAGE)

    return render(
        request,
        "diplomas/diploma_search.html",
        {
            "search_term": search_term,
            "status_filter": status_filter,
            "year_filter": year_filter,
            "page_obj": page,
            "results": page.object_list if page else None,
            "status_choices": Diplome.Status.choices,
            "status_counts": get_diploma_status_counts(request.user),
            "base_querystring": querystring_without(request, "page"),
        },
    )


def _csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # BOM : ouverture directe dans Excel
    writer = csv.writer(response, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    return response


@login_required
def registry_export(request):
    _require_access(request.user)
    lots, _ = _filter_lots(request, get_visible_lots(request.user))

    rows = [
        [
            lot.reference,
            lot.etablissement,
            lot.date_arrivee.strftime("%d/%m/%Y") if lot.date_arrivee else "",
            lot.nombre_annonce,
            lot.nombre_conformes,
            lot.ecart,
            lot.nombre_anomalies,
            lot.get_statut_display(),
            timezone.localtime(lot.date_transmission_dg).strftime("%d/%m/%Y %H:%M")
            if lot.date_transmission_dg
            else "",
            timezone.localtime(lot.date_signature).strftime("%d/%m/%Y %H:%M") if lot.date_signature else "",
        ]
        for lot in lots
    ]

    log_activity(request.user, "Export du registre des lots de diplômes", "Diplômes", f"{len(rows)} lot(s)")
    return _csv_response(
        f"registre-lots-diplomes-{timezone.localdate():%Y%m%d}.csv",
        [
            "Référence",
            "Établissement",
            "Date d'arrivée",
            "Nombre annoncé",
            "Conformes",
            "Incohérence",
            "Non conformes",
            "Statut",
            "Transmission DG",
            "Signature",
        ],
        rows,
    )


@login_required
def lot_export(request, pk):
    _require_access(request.user)
    lot = get_object_or_404(get_visible_lots(request.user), pk=pk)

    rows = [
        [
            diplome.nom_beneficiaire,
            diplome.numero_diplome,
            diplome.filiere,
            diplome.etablissement_effectif,
            diplome.annee_academique,
            diplome.get_statut_display(),
            diplome.get_anomalie_display() if diplome.anomalie else "",
            diplome.observations,
        ]
        for diplome in lot.diplomes.all()
    ]

    log_activity(request.user, "Export des diplômes d'un lot", "Diplômes", lot.reference)
    return _csv_response(
        f"{lot.reference.lower()}-diplomes.csv",
        [
            "Nom du bénéficiaire",
            "Numéro du diplôme",
            "Filière",
            "Établissement",
            "Année académique",
            "Statut",
            "Anomalie",
            "Observations",
        ],
        rows,
    )

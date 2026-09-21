import csv
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.permissions import (
    can_access_courriers,
    can_manage_courriers,
    can_record_dg_decision,
    can_transmit_to_dg,
    can_validate_as_dg,
    is_admin_user,
)
from core.utils import log_activity, paginate, querystring_without, safe_next_url

from .forms import CourrierForm, FicheAnalyseForm
from .models import Courrier, InstructionCourrier
from .selectors import get_status_counts, get_visible_courriers
from .services import (
    build_imputation_grid,
    create_tasks_from_imputations,
    decouper_en_rangees,
    register_history,
)
from .workflow import apply_transition, get_available_transitions

COURRIERS_PER_PAGE = 25


def _require_management(user):
    if not can_manage_courriers(user):
        raise PermissionDenied


def _require_access(user):
    if not can_access_courriers(user):
        raise PermissionDenied


def _filter_courriers(request, courriers):
    statut = request.GET.get("statut", "").strip()
    sens = request.GET.get("sens", "").strip()
    nature = request.GET.get("nature", "").strip()
    priorite = request.GET.get("priorite", "").strip()
    recherche = request.GET.get("q", "").strip()
    libelle = ""

    if statut:
        courriers = courriers.filter(statut=statut)
        try:
            libelle = Courrier.Status(statut).label
        except ValueError:
            libelle = ""
    if sens:
        courriers = courriers.filter(sens=sens)
    if nature:
        courriers = courriers.filter(nature=nature)
        try:
            libelle = libelle or Courrier.Nature(nature).label
        except ValueError:
            pass
    if priorite:
        courriers = courriers.filter(priorite=priorite)
        if priorite == Courrier.Priorite.URGENTE:
            libelle = libelle or "Courriers urgents"
    if recherche:
        courriers = courriers.filter(
            Q(reference__icontains=recherche)
            | Q(objet__icontains=recherche)
            | Q(expediteur__icontains=recherche)
            | Q(observation__icontains=recherche)
            | Q(destinataire_service__nom__icontains=recherche)
            # Les deux sens se cherchent de la même façon : le nom tapé peut
            # être celui d'un expéditeur externe comme d'un destinataire.
            | Q(service_emetteur__nom__icontains=recherche)
            | Q(destinataire_externe__nom__icontains=recherche)
        )

    return courriers, {
        "status_filter": statut,
        "sens_filter": sens,
        "nature_filter": nature,
        "priorite_filter": priorite,
        "search_term": recherche,
        "active_filter_label": libelle,
    }


@login_required
def courrier_list(request):
    courriers, filtres = _filter_courriers(request, get_visible_courriers(request.user))
    page = paginate(request, courriers, COURRIERS_PER_PAGE)

    context = {
        "page_obj": page,
        "courriers": page.object_list,
        "status_counts": get_status_counts(request.user),
        "status_choices": Courrier.Status.choices,
        "sens_choices": Courrier.Sens.choices,
        "nature_choices": Courrier.Nature.choices,
        "priorite_choices": Courrier.Priorite.choices,
        "can_manage": can_manage_courriers(request.user),
        "can_access": can_access_courriers(request.user),
        "can_delete": is_admin_user(request.user),
        "total_courriers": page.paginator.count,
        "base_querystring": querystring_without(request, "page"),
        **filtres,
    }
    return render(request, "courriers/list.html", context)


@login_required
def courrier_create(request):
    _require_management(request.user)

    if request.method == "POST":
        form = CourrierForm(request.POST, request.FILES)
        if form.is_valid():
            courrier = form.save(commit=False)
            courrier.cree_par = request.user
            if not courrier.receptionne_par:
                courrier.receptionne_par = request.user
            courrier.save()
            register_history(courrier, request.user, "Réception du courrier", "", courrier.statut)
            log_activity(request.user, "Réception d'un courrier", "Courriers", courrier.reference)
            messages.success(
                request,
                f"Le courrier {courrier.reference} a été enregistré.",
            )
            return redirect("courriers:detail", pk=courrier.pk)
    else:
        initial = {"date_reception": timezone.localdate()}
        profile = getattr(request.user, "profil", None)
        if profile and profile.service_id:
            initial["destinataire_service"] = profile.service
        form = CourrierForm(initial=initial)

    return render(
        request,
        "courriers/form.html",
        {
            "form": form,
            "title": "Enregistrer un courrier",
            "is_creation": True,
        },
    )


@login_required
def courrier_edit(request, pk):
    _require_management(request.user)
    courrier = get_object_or_404(get_visible_courriers(request.user), pk=pk)

    if courrier.statut not in {Courrier.Status.RECU, Courrier.Status.EN_TRAITEMENT}:
        messages.error(
            request,
            "Ce courrier est déjà engagé dans le circuit de visa : sa fiche n'est plus modifiable.",
        )
        return redirect("courriers:detail", pk=courrier.pk)

    ancien_fichier = courrier.fichier.name if courrier.fichier else ""

    if request.method == "POST":
        form = CourrierForm(request.POST, request.FILES, instance=courrier)
        if form.is_valid():
            courrier = form.save()
            if (
                form.cleaned_data.get("fichier")
                and ancien_fichier
                and ancien_fichier != courrier.fichier.name
            ):
                courrier.fichier.storage.delete(ancien_fichier)
            register_history(
                courrier,
                request.user,
                "Mise à jour de la fiche",
                courrier.statut,
                courrier.statut,
            )
            log_activity(request.user, "Mise à jour d'un courrier", "Courriers", courrier.reference)
            messages.success(request, "La fiche du courrier a été mise à jour.")
            return redirect("courriers:detail", pk=courrier.pk)
    else:
        form = CourrierForm(instance=courrier)

    return render(
        request,
        "courriers/form.html",
        {
            "form": form,
            "courrier": courrier,
            "title": f"Modifier {courrier.reference}",
            "is_creation": False,
        },
    )


@login_required
def courrier_detail(request, pk):
    courrier = get_object_or_404(get_visible_courriers(request.user), pk=pk)

    steps = [
        {
            "key": statut,
            "label": Courrier.Status(statut).label,
            "index": index + 1,
            "is_done": bool(courrier.etape_index) and index + 1 < courrier.etape_index,
            "is_current": index + 1 == courrier.etape_index,
        }
        for index, statut in enumerate(Courrier.STATUS_FLOW)
    ]

    return render(
        request,
        "courriers/detail.html",
        {
            "courrier": courrier,
            "steps": steps,
            "transitions": get_available_transitions(courrier, request.user),
            "histories": courrier.historiques.select_related("utilisateur")[:30],
            "taches": courrier.taches.select_related("assigne_a", "service_concerne"),
            "taches_ouvertes": courrier.taches_ouvertes.count(),
            "suite_donnee": courrier.suite_donnee,
            "can_manage": can_manage_courriers(request.user),
            "can_sign": can_validate_as_dg(request.user),
            "can_transmit": can_transmit_to_dg(request.user),
            "can_record_fiche": can_record_dg_decision(request.user)
            and courrier.statut == Courrier.Status.TRANSMIS_DG,
            "can_delete": is_admin_user(request.user),
            "can_edit_sheet": courrier.statut
            in {Courrier.Status.RECU, Courrier.Status.EN_TRAITEMENT},
        },
    )


@login_required
def courrier_fiche(request, pk):
    """Saisie de la fiche d'analyse : imputations, instructions, observations.

    Ouverte au Directeur General et au Secretariat. Quand c'est le secretariat
    qui saisit, la fiche porte la mention « pour le compte du DG » : la
    decision reste celle du DG, la frappe est celle de la secretaire.
    """
    if not can_record_dg_decision(request.user):
        raise PermissionDenied

    courrier = get_object_or_404(get_visible_courriers(request.user), pk=pk)
    if courrier.statut != Courrier.Status.TRANSMIS_DG:
        messages.error(
            request,
            "La fiche d'analyse ne peut etre renseignee qu'une fois le courrier transmis au DG.",
        )
        return redirect("courriers:detail", pk=courrier.pk)

    pour_le_compte_du_dg = not can_validate_as_dg(request.user)

    if request.method == "POST":
        form = FicheAnalyseForm(request.POST, instance=courrier)
        if form.is_valid():
            courrier = form.save(commit=False)
            courrier.date_fiche = timezone.now()
            courrier.fiche_saisie_par = request.user
            courrier.fiche_pour_le_compte_du_dg = pour_le_compte_du_dg
            courrier.save()
            form.save_m2m()

            mention = " (reportée par le secrétariat)" if pour_le_compte_du_dg else ""
            register_history(
                courrier,
                request.user,
                f"Fiche d'analyse renseignée{mention}",
                courrier.statut,
                courrier.statut,
                commentaire=courrier.instruction_dg,
            )
            log_activity(request.user, "Fiche d'analyse renseignée", "Courriers", courrier.reference)

            details = ""
            if form.cleaned_data.get("ouvrir_des_taches"):
                total = create_tasks_from_imputations(courrier, request.user)
                if total:
                    details = f" {total} tâche(s) de suivi ouverte(s)."
                    register_history(
                        courrier,
                        request.user,
                        f"{total} tâche(s) de suivi ouverte(s) par imputation",
                        courrier.statut,
                        courrier.statut,
                    )

            messages.success(
                request,
                "La fiche d'analyse a été enregistrée."
                + (
                    " Elle est marquée comme reportée pour le compte du Directeur Général."
                    if pour_le_compte_du_dg
                    else ""
                )
                + details,
            )
            return redirect("courriers:detail", pk=courrier.pk)
    else:
        form = FicheAnalyseForm(instance=courrier)

    return render(
        request,
        "courriers/fiche_form.html",
        {
            "form": form,
            "courrier": courrier,
            "pour_le_compte_du_dg": pour_le_compte_du_dg,
        },
    )


@login_required
def courrier_fiche_print(request, pk):
    """Fiche d'analyse au format du formulaire papier, prête à imprimer.

    Le secrétariat l'imprime avant la remise au Directeur Général : les
    rubriques qu'il renseigne restent vierges pour être annotées à la main.
    """
    _require_access(request.user)
    courrier = get_object_or_404(
        get_visible_courriers(request.user).prefetch_related(
            "services_imputes",
            "agents_imputes",
            "instructions",
        ),
        pk=pk,
    )

    services_coches = set(courrier.services_imputes.values_list("id", flat=True))
    agents_coches = set(courrier.agents_imputes.values_list("id", flat=True))
    instructions_cochees = {item.pk for item in courrier.instructions.all()}

    grille = [
        {
            "service": entree["service"],
            "service_cochee": entree["service"].pk in services_coches,
            "agents": [
                {
                    "nom": agent.get_full_name().strip() or agent.username,
                    "cochee": agent.pk in agents_coches,
                }
                for agent in entree["agents"]
            ],
        }
        for entree in build_imputation_grid()
    ]

    return render(
        request,
        "courriers/fiche_print.html",
        {
            "courrier": courrier,
            "rangees_imputations": decouper_en_rangees(grille),
            "instructions": [
                {"objet": instruction, "cochee": instruction.pk in instructions_cochees}
                for instruction in InstructionCourrier.objects.filter(actif=True)
            ],
        },
    )


@login_required
def courrier_decharge(request, pk):
    """Décharge accompagnant un courrier sortant, prête à imprimer.

    Elle part avec le courrier et revient signée : c'est le destinataire, à
    l'extérieur de la DGES, qui la remplit à la remise. Tout ce qui le
    concerne — son nom, sa fonction, la date et l'heure auxquelles il reçoit,
    le nombre de pièces qu'il compte — est donc inconnu à l'impression et
    reste vierge. Pré-remplir ces rubriques reviendrait à attester de faits
    qui ne se sont pas encore produits.

    Un courrier entrant n'en a pas : la DGES le reçoit, elle ne le remet à
    personne.
    """
    _require_access(request.user)
    courrier = get_object_or_404(
        get_visible_courriers(request.user).select_related(
            "service_emetteur",
            "destinataire_externe",
        ),
        pk=pk,
    )

    if not courrier.est_sortant:
        raise Http404("La décharge ne concerne que les courriers sortants.")

    return render(request, "courriers/decharge_print.html", {"courrier": courrier})


@login_required
@require_POST
def courrier_status(request, pk, statut):
    _require_access(request.user)
    courrier = get_object_or_404(get_visible_courriers(request.user), pk=pk)

    succes, message = apply_transition(
        courrier,
        statut,
        request.user,
        commentaire=request.POST.get("commentaire", ""),
        instruction=request.POST.get("instruction", ""),
    )
    if succes:
        messages.success(request, message)
        log_activity(request.user, f"Courrier : {message}", "Courriers", courrier.reference)
    else:
        messages.error(request, message)

    return redirect(safe_next_url(request, request.POST.get("next"), "courriers:list"))


@login_required
def courrier_download(request, pk):
    courrier = get_object_or_404(get_visible_courriers(request.user), pk=pk)
    if not courrier.fichier:
        raise Http404("Aucune pièce numérisée pour ce courrier.")

    type_devine = mimetypes.guess_type(courrier.fichier.name)[0] or "application/octet-stream"
    response = FileResponse(
        courrier.fichier.open("rb"),
        as_attachment=True,
        filename=courrier.nom_fichier,
        content_type=type_devine,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def courrier_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    courrier = get_object_or_404(Courrier, pk=pk)
    reference = courrier.reference
    if courrier.fichier:
        courrier.fichier.delete(save=False)
    courrier.delete()
    log_activity(request.user, "Suppression d'un courrier", "Courriers", reference)
    messages.success(request, f"Le courrier {reference} a été supprimé.")
    return redirect(safe_next_url(request, request.POST.get("next"), "courriers:list"))


@login_required
def courrier_export(request):
    _require_access(request.user)
    courriers, _ = _filter_courriers(request, get_visible_courriers(request.user))

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="registre-courriers-{timezone.localdate():%Y%m%d}.csv"'
    )
    response.write("﻿")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Référence",
            "Sens",
            "Nature",
            "Objet",
            "Provenance",
            "Destinataire",
            "Réception",
            "Priorité",
            "Statut",
            "Transmission DG",
            "Visa DG",
            "Instruction",
        ]
    )
    for courrier in courriers:
        writer.writerow(
            [
                courrier.reference,
                courrier.get_sens_display(),
                courrier.get_nature_display(),
                courrier.objet,
                courrier.provenance,
                courrier.destinataire,
                courrier.date_reception.strftime("%d/%m/%Y") if courrier.date_reception else "",
                courrier.get_priorite_display(),
                courrier.get_statut_display(),
                timezone.localtime(courrier.date_transmission_dg).strftime("%d/%m/%Y %H:%M")
                if courrier.date_transmission_dg
                else "",
                timezone.localtime(courrier.date_visa).strftime("%d/%m/%Y %H:%M")
                if courrier.date_visa
                else "",
                courrier.instruction_dg,
            ]
        )

    log_activity(request.user, "Export du registre des courriers", "Courriers", f"{courriers.count()} courrier(s)")
    return response

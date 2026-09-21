from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.permissions import (
    can_access_bordereaux,
    can_manage_bordereaux,
    is_admin_user,
)
from core.utils import csv_response, log_activity, paginate, querystring_without, safe_next_url

from .forms import BordereauForm, OrganismeForm, SignatureForm, initial_bordereau
from .models import Bordereau, Organisme, Trimestre, TRIMESTRE_PERIODES
from .selectors import (
    filtrer_par_etat,
    get_annees_suivies,
    get_bordereaux_de_la_boite,
    get_bordereaux_scope,
    get_compteurs_periode,
    get_organismes,
    get_tableau_annuel,
)
from .services import (
    decrire_changement,
    register_bordereau_history,
    signer_engagement,
    signer_liquidation,
)

BORDEREAUX_PAR_PAGE = 25
ORGANISMES_PAR_PAGE = 30

# Les deux signatures suivies, et la fonction qui sait les enregistrer.
SIGNATURES = {
    "engagement": {
        "libelle": "l'engagement",
        "action": signer_engagement,
    },
    "liquidation": {
        "libelle": "la liquidation",
        "action": signer_liquidation,
    },
}


def _require_access(user):
    """Consultation du suivi : Secretariat, Secretariat adjoint, DG."""
    if not can_access_bordereaux(user):
        raise PermissionDenied


def _require_management(user):
    """Saisie d'un bordereau ou d'une signature."""
    if not can_manage_bordereaux(user):
        raise PermissionDenied


def _annee_demandee(request, annee=None):
    """Annee affichee : celle de l'URL, sinon la derniere suivie, sinon l'annee en cours."""
    if annee:
        return annee
    annees = get_annees_suivies(request.user)
    return annees[0] if annees else timezone.localdate().year


def _contexte_commun(request, annee):
    annees = get_annees_suivies(request.user)
    if annee not in annees:
        annees = sorted({annee, *annees}, reverse=True)
    return {
        "annee": annee,
        "annees": annees,
        "can_manage": can_manage_bordereaux(request.user),
        "can_delete": is_admin_user(request.user),
    }


# ------------------------------------------------------------ tableau annuel


@login_required
def tableau(request, annee=None):
    """Grille Annee -> Organisme -> quatre boites trimestrielles."""
    _require_access(request.user)
    annee = _annee_demandee(request, annee)

    recherche = request.GET.get("q", "").strip()
    organismes = get_organismes()
    if recherche:
        organismes = organismes.filter(
            Q(nom__icontains=recherche) | Q(sigle__icontains=recherche)
        )

    page = paginate(request, organismes, ORGANISMES_PAR_PAGE)
    lignes = get_tableau_annuel(request.user, annee, page.object_list)

    context = {
        **_contexte_commun(request, annee),
        "lignes": lignes,
        "page_obj": page,
        "recherche": recherche,
        "resume": get_compteurs_periode(request.user, annee),
        "periodes": [
            {
                "valeur": trimestre.value,
                "label": trimestre.label,
                "periode": TRIMESTRE_PERIODES[trimestre],
            }
            for trimestre in Trimestre
        ],
        "base_querystring": querystring_without(request, "page"),
        "total_organismes": page.paginator.count,
    }
    return render(request, "bordereaux/tableau.html", context)


@login_required
def boite(request, annee, trimestre, organisme_pk):
    """Contenu d'une boite trimestrielle : les bordereaux et leur etat."""
    _require_access(request.user)
    organisme = get_object_or_404(Organisme, pk=organisme_pk)
    trimestre = Trimestre(trimestre)

    etat_filtre = request.GET.get("etat", "").strip()
    recherche = request.GET.get("q", "").strip()

    bordereaux = get_bordereaux_de_la_boite(request.user, annee, trimestre.value, organisme)
    if etat_filtre:
        bordereaux = filtrer_par_etat(bordereaux, etat_filtre)
    if recherche:
        bordereaux = bordereaux.filter(
            Q(numero__icontains=recherche) | Q(observation__icontains=recherche)
        )

    page = paginate(request, bordereaux, BORDEREAUX_PAR_PAGE)
    compteurs = get_compteurs_periode(request.user, annee, trimestre.value, organisme)

    context = {
        **_contexte_commun(request, annee),
        "organisme": organisme,
        "trimestre": trimestre.value,
        "trimestre_label": trimestre.label,
        "periode": TRIMESTRE_PERIODES[trimestre],
        "bordereaux": page.object_list,
        "page_obj": page,
        "compteurs": compteurs,
        "etat_filtre": etat_filtre,
        "recherche": recherche,
        "etats": Bordereau.Etat.choices,
        "base_querystring": querystring_without(request, "page"),
    }
    return render(request, "bordereaux/boite.html", context)


# ---------------------------------------------------------------- bordereaux


@login_required
def bordereau_create(request):
    _require_management(request.user)

    if request.method == "POST":
        # request.FILES est indispensable : sans lui le bordereau joint est
        # ignore en silence, et le formulaire se valide quand meme.
        form = BordereauForm(request.POST, request.FILES)
        if form.is_valid():
            bordereau = form.save(commit=False)
            bordereau.cree_par = request.user
            bordereau.save()
            register_bordereau_history(
                bordereau,
                request.user,
                "Enregistrement du bordereau",
                "",
                bordereau.etat,
            )
            log_activity(
                request.user,
                "Enregistrement d'un bordereau",
                "Bordereaux",
                f"{bordereau.organisme.libelle_court} / {bordereau.libelle}",
            )
            messages.success(
                request,
                f"Le bordereau {bordereau.libelle} a été enregistré "
                f"dans la boîte {bordereau.periode_label}."
                + (
                    ""
                    if bordereau.est_numerote
                    else " Son numéro pourra être renseigné plus tard."
                ),
            )
            if "save_and_add" in request.POST:
                # Enchainer la saisie d'une pile de bordereaux : on revient au
                # formulaire vide, deja cale sur la meme boite trimestrielle.
                return redirect(
                    f"{reverse('bordereaux:create')}?organisme={bordereau.organisme_id}"
                    f"&annee={bordereau.annee}&trimestre={bordereau.trimestre}"
                )
            return redirect("bordereaux:detail", pk=bordereau.pk)
    else:
        form = BordereauForm(initial=_initial_depuis_url(request))

    return render(
        request,
        "bordereaux/form.html",
        {
            "form": form,
            "titre": "Enregistrer un bordereau",
            "is_creation": True,
            "retour": _retour_depuis_url(request),
        },
    )


def _initial_depuis_url(request):
    """Pre-remplit la saisie avec la boite d'ou vient l'utilisateur."""
    organisme = None
    organisme_pk = request.GET.get("organisme")
    if organisme_pk:
        organisme = Organisme.objects.filter(pk=organisme_pk).first()

    def entier(nom):
        valeur = request.GET.get(nom)
        return int(valeur) if valeur and valeur.isdigit() else None

    return initial_bordereau(
        organisme=organisme,
        annee=entier("annee"),
        trimestre=entier("trimestre"),
    )


def _retour_depuis_url(request):
    """Lien « Annuler » ramenant a la boite d'origine quand elle est connue."""
    return safe_next_url(request, request.GET.get("next"), "bordereaux:tableau")


@login_required
def bordereau_detail(request, pk):
    _require_access(request.user)
    bordereau = get_object_or_404(get_bordereaux_scope(request.user), pk=pk)

    etapes = [
        {
            "titre": "Engagement",
            "description": "Signature initiale du dossier. Le bordereau entre dans le circuit.",
            "date": bordereau.date_engagement,
            "fait": bordereau.engagement_signe,
            "mention": "" if bordereau.engagement_signe else "En attente",
        },
        {
            "titre": "Mandat",
            "description": "Validation par le Contrôleur financier.",
            "date": None,
            "fait": bordereau.mandat_deduit,
            # Le mandat n'a pas de date propre : il se deduit de la liquidation.
            "mention": bordereau.mandat_label,
        },
        {
            "titre": "Liquidation",
            "description": "Dernière signature suivie. Elle clôt le circuit.",
            "date": bordereau.date_liquidation,
            "fait": bordereau.liquidation_signee,
            "mention": "" if bordereau.liquidation_signee else "En attente",
        },
    ]

    return render(
        request,
        "bordereaux/detail.html",
        {
            **_contexte_commun(request, bordereau.annee),
            "bordereau": bordereau,
            "etapes": etapes,
            "signature_form": SignatureForm(initial={"date_signature": timezone.localdate()}),
            "historiques": bordereau.historiques.select_related("utilisateur")[:30],
        },
    )


@login_required
def bordereau_edit(request, pk):
    _require_management(request.user)
    bordereau = get_object_or_404(get_bordereaux_scope(request.user), pk=pk)
    ancien_etat = bordereau.etat

    if request.method == "POST":
        form = BordereauForm(request.POST, request.FILES, instance=bordereau)
        if form.is_valid():
            bordereau = form.save()
            register_bordereau_history(
                bordereau,
                request.user,
                decrire_changement(ancien_etat, bordereau.etat),
                ancien_etat,
                bordereau.etat,
            )
            log_activity(
                request.user,
                "Mise à jour d'un bordereau",
                "Bordereaux",
                f"{bordereau.organisme.libelle_court} / {bordereau.libelle}",
            )
            messages.success(request, "La fiche du bordereau a été mise à jour.")
            return redirect("bordereaux:detail", pk=bordereau.pk)
    else:
        form = BordereauForm(instance=bordereau)

    return render(
        request,
        "bordereaux/form.html",
        {
            "form": form,
            "bordereau": bordereau,
            "titre": f"Modifier {bordereau.libelle}",
            "is_creation": False,
            "retour": reverse("bordereaux:detail", args=[bordereau.pk]),
        },
    )


@login_required
@require_POST
def bordereau_signer(request, pk, etape):
    """Enregistre une signature depuis la fiche du bordereau."""
    _require_management(request.user)
    signature = SIGNATURES.get(etape)
    if signature is None:
        raise PermissionDenied

    bordereau = get_object_or_404(get_bordereaux_scope(request.user), pk=pk)
    form = SignatureForm(request.POST)

    if not form.is_valid():
        messages.error(request, f"Date de signature de {signature['libelle']} invalide.")
        return redirect("bordereaux:detail", pk=bordereau.pk)

    reussi, message = signature["action"](
        bordereau,
        request.user,
        form.cleaned_data["date_signature"],
        form.cleaned_data.get("commentaire", ""),
    )

    if reussi:
        messages.success(request, message)
        log_activity(
            request.user,
            f"Signature de {signature['libelle']} d'un bordereau",
            "Bordereaux",
            f"{bordereau.organisme.libelle_court} / {bordereau.libelle}",
        )
    else:
        messages.error(request, message)

    return redirect(safe_next_url(request, request.POST.get("next"), "bordereaux:tableau"))


@login_required
@require_POST
def bordereau_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    bordereau = get_object_or_404(Bordereau, pk=pk)
    libelle = f"{bordereau.organisme.libelle_court} / {bordereau.libelle}"
    bordereau.delete()
    log_activity(request.user, "Suppression d'un bordereau", "Bordereaux", libelle)
    messages.success(request, f"Le bordereau {libelle} a été supprimé.")
    return redirect(safe_next_url(request, request.POST.get("next"), "bordereaux:tableau"))


@login_required
def bordereau_fichier(request, pk):
    """Sert le bordereau joint.

    La piece ne sort jamais en direct du dossier des medias : elle passe par
    cette vue, qui verifie d'abord que le compte a le droit de voir ce
    bordereau.

    Avec `?consulter=1`, un PDF s'ouvre dans la fiche au lieu d'etre
    telecharge — c'est l'usage courant : on regarde le bordereau pendant
    qu'on releve ses dates de signature.

    Seul le PDF est servi ainsi. Un document Word ou une image sont toujours
    telecharges : servir en ligne un fichier depose reviendrait a le laisser
    decider de la facon dont il est interprete.
    """
    _require_access(request.user)
    bordereau = get_object_or_404(get_bordereaux_scope(request.user), pk=pk)
    if not bordereau.fichier:
        raise Http404("Aucun bordereau n'est joint à cette fiche.")

    nom = Path(bordereau.fichier.name).name
    est_pdf = nom.lower().endswith(".pdf")
    consulter = request.GET.get("consulter") == "1" and est_pdf

    if not consulter:
        log_activity(
            request.user,
            "Téléchargement d'un bordereau",
            "Bordereaux",
            f"{bordereau.organisme.libelle_court} / {bordereau.libelle}",
        )

    reponse = FileResponse(
        bordereau.fichier.open("rb"),
        as_attachment=not consulter,
        filename=nom,
        content_type="application/pdf" if est_pdf else None,
    )
    # Le navigateur doit s'en tenir au type annonce et ne pas le deviner a
    # partir du contenu : c'est ce qui empeche un fichier depose de se faire
    # passer pour autre chose.
    reponse["X-Content-Type-Options"] = "nosniff"

    if consulter:
        # Sans cet en-tete, l'apercu echoue : l'intergiciel anti-detournement
        # de clic pose « X-Frame-Options: DENY » sur toutes les reponses. On
        # ouvre le cadre a notre seule origine ; l'intergiciel respecte un
        # en-tete deja pose et ne l'ecrase pas.
        reponse["X-Frame-Options"] = "SAMEORIGIN"
    return reponse


# ---------------------------------------------------------------- organismes


@login_required
def organisme_list(request):
    _require_access(request.user)
    recherche = request.GET.get("q", "").strip()
    organismes = get_organismes(actifs_seulement=False)
    if recherche:
        organismes = organismes.filter(
            Q(nom__icontains=recherche) | Q(sigle__icontains=recherche)
        )

    page = paginate(request, organismes, ORGANISMES_PAR_PAGE)
    return render(
        request,
        "bordereaux/organisme_list.html",
        {
            "organismes": page.object_list,
            "page_obj": page,
            "recherche": recherche,
            "can_manage": can_manage_bordereaux(request.user),
            "can_delete": is_admin_user(request.user),
            "base_querystring": querystring_without(request, "page"),
            "annee": _annee_demandee(request),
        },
    )


@login_required
def organisme_create(request):
    _require_management(request.user)
    return _organisme_form(request, None)


@login_required
def organisme_edit(request, pk):
    _require_management(request.user)
    return _organisme_form(request, get_object_or_404(Organisme, pk=pk))


def _organisme_form(request, organisme):
    creation = organisme is None

    if request.method == "POST":
        form = OrganismeForm(request.POST, instance=organisme)
        if form.is_valid():
            organisme = form.save()
            log_activity(
                request.user,
                "Enregistrement d'un organisme" if creation else "Mise à jour d'un organisme",
                "Bordereaux",
                organisme.libelle_complet,
            )
            messages.success(
                request,
                f"L'organisme {organisme.libelle_court} a été "
                f"{'enregistré' if creation else 'mis à jour'}.",
            )
            return redirect("bordereaux:organisme_list")
    else:
        form = OrganismeForm(instance=organisme)

    return render(
        request,
        "bordereaux/organisme_form.html",
        {
            "form": form,
            "organisme": organisme,
            "titre": "Ajouter un organisme" if creation else f"Modifier {organisme.libelle_court}",
            "is_creation": creation,
        },
    )


@login_required
@require_POST
def organisme_delete(request, pk):
    if not is_admin_user(request.user):
        raise PermissionDenied

    organisme = get_object_or_404(Organisme, pk=pk)
    libelle = organisme.libelle_court
    try:
        organisme.delete()
    except ProtectedError:
        # Supprimer l'organisme emporterait des bordereaux deja signes :
        # le desactiver le retire du tableau sans effacer l'historique.
        messages.error(
            request,
            f"{libelle} a des bordereaux enregistrés : décochez « Organisme suivi » "
            "pour le retirer du tableau sans perdre son historique.",
        )
        return redirect("bordereaux:organisme_list")

    log_activity(request.user, "Suppression d'un organisme", "Bordereaux", libelle)
    messages.success(request, f"L'organisme {libelle} a été supprimé.")
    return redirect("bordereaux:organisme_list")


# -------------------------------------------------------------------- export


@login_required
def export(request, annee=None):
    """Registre de l'annee au format CSV, sans aucun montant."""
    _require_access(request.user)
    annee = _annee_demandee(request, annee)

    bordereaux = get_bordereaux_scope(request.user).filter(annee=annee).order_by(
        "organisme__nom", "trimestre", "numero"
    )
    trimestre = request.GET.get("trimestre", "").strip()
    if trimestre.isdigit():
        bordereaux = bordereaux.filter(trimestre=int(trimestre))
    organisme_pk = request.GET.get("organisme", "").strip()
    if organisme_pk.isdigit():
        bordereaux = bordereaux.filter(organisme_id=int(organisme_pk))

    lignes = [
        [
            bordereau.annee,
            bordereau.get_trimestre_display(),
            bordereau.organisme.libelle_court,
            bordereau.numero,
            bordereau.date_reception.strftime("%d/%m/%Y") if bordereau.date_reception else "",
            bordereau.date_engagement.strftime("%d/%m/%Y") if bordereau.date_engagement else "",
            "Oui" if bordereau.mandat_deduit else "Non",
            bordereau.date_liquidation.strftime("%d/%m/%Y") if bordereau.date_liquidation else "",
            bordereau.etat_label,
            bordereau.observation,
        ]
        for bordereau in bordereaux
    ]

    log_activity(
        request.user,
        "Export du suivi des bordereaux",
        "Bordereaux",
        f"{annee} — {len(lignes)} bordereau(x)",
    )
    return csv_response(
        f"suivi-bordereaux-{annee}.csv",
        [
            "Année",
            "Trimestre",
            "Organisme",
            "N° de bordereau",
            "Date de réception",
            "Signature engagement",
            "Mandat déduit",
            "Signature liquidation",
            "État",
            "Observation",
        ],
        lignes,
    )

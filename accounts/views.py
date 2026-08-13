import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import ConnexionLog
from core.permissions import can_manage_accounts, can_view_accounts, capability_required
from core.utils import log_activity, paginate, querystring_without, safe_next_url
from messagerie.services import desactiver_acces_messagerie, synchroniser_sans_bloquer

from .constants import ROLE_CHOICES, ROLE_GROUP_NAMES
from .forms import (
    AgentUserCreationForm,
    AgentUserUpdateForm,
    ConnexionForm,
    MotDePasseChangeForm,
    ServiceForm,
    UserProfileForm,
)
from .models import Service, UserProfile

# Description des capacites par role, pour la page de synthese des acces.
# Le tableau reste dans la vue : il documente la matrice de `constants.py`
# a destination de l'administrateur, il ne la definit pas.
CAPACITES_PAR_ROLE = {
    "directeur_general": ["Validation générale", "Signature", "Vue sur toute l'activité"],
    "administrateur": ["Comptes et accès", "Services", "Administration technique"],
    "secretariat": ["Visa et transmission au DG", "Planning de la direction", "Visiteurs"],
    "secretariat_adjoint": ["Courriers", "Visiteurs", "Planning du DG"],
    "courrier": ["Réception et traitement du courrier"],
    "agent_etude": ["Lots de diplômes", "Vérification et validation"],
    "agent": ["Ses propres tâches", "Documentation partagée"],
}


class DGESLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = ConnexionForm
    redirect_authenticated_user = True


class DGESLogoutView(LogoutView):
    next_page = "accounts:login"


@capability_required(can_view_accounts)
def access_panel(request):
    """Panneau general d'acces : qui existe, avec quel role, dans quel service."""
    profils = UserProfile.objects.select_related("utilisateur")
    total_comptes = profils.count()
    total_actifs = profils.filter(actif=True, utilisateur__is_active=True).count()

    totaux_par_role = {
        row["role"]: row["total"]
        for row in profils.values("role").annotate(total=Count("id"))
    }
    maximum = max(totaux_par_role.values()) if totaux_par_role else 0

    # Categories nominales : une seule couleur pour toutes les barres. La
    # longueur porte la grandeur, la couleur ne double pas l'information.
    roles = [
        {
            "cle": cle,
            "libelle": libelle,
            "total": totaux_par_role.get(cle, 0),
            "largeur": round(totaux_par_role.get(cle, 0) * 100 / maximum) if maximum else 0,
            "groupe": ROLE_GROUP_NAMES.get(cle, ""),
            "capacites": CAPACITES_PAR_ROLE.get(cle, []),
        }
        for cle, libelle in ROLE_CHOICES
    ]

    services = Service.objects.annotate(
        membres_total=Count("membres", distinct=True)
    ).order_by("nom")

    context = {
        "roles": roles,
        "services": services,
        "stats": {
            "total_comptes": total_comptes,
            "total_actifs": total_actifs,
            "total_inactifs": total_comptes - total_actifs,
            "total_services": services.count(),
            "services_actifs": sum(1 for service in services if service.actif),
            "mots_de_passe_a_changer": profils.filter(doit_changer_mot_de_passe=True).count(),
        },
        "can_edit": can_manage_accounts(request.user),
    }
    return render(request, "accounts/access_panel.html", context)


@capability_required(can_view_accounts)
def user_list(request):
    search_term = request.GET.get("q", "").strip()
    role_filter = request.GET.get("role", "").strip()
    etat_filter = request.GET.get("etat", "").strip()
    profiles = UserProfile.objects.select_related("utilisateur", "service")

    if role_filter:
        profiles = profiles.filter(role=role_filter)
    if etat_filter == "actif":
        profiles = profiles.filter(actif=True, utilisateur__is_active=True)
    elif etat_filter == "inactif":
        profiles = profiles.filter(Q(actif=False) | Q(utilisateur__is_active=False))

    if search_term:
        profiles = profiles.filter(
            Q(utilisateur__username__icontains=search_term)
            | Q(utilisateur__first_name__icontains=search_term)
            | Q(utilisateur__last_name__icontains=search_term)
            | Q(service__nom__icontains=search_term)
            | Q(fonction__icontains=search_term)
        )

    context = {
        "profiles": profiles,
        "search_term": search_term,
        "role_filter": role_filter,
        "etat_filter": etat_filter,
        "role_choices": ROLE_CHOICES,
        "can_edit": can_manage_accounts(request.user),
        "can_delete": can_manage_accounts(request.user),
    }
    return render(request, "accounts/user_list.html", context)


@capability_required(can_view_accounts)
def connexion_history(request):
    """Historique des connexions : qui s'est connecté, quand, depuis quel poste."""
    resultat_filter = request.GET.get("resultat", "").strip()
    recherche = request.GET.get("q", "").strip()

    connexions = ConnexionLog.objects.select_related("utilisateur")
    if resultat_filter:
        connexions = connexions.filter(resultat=resultat_filter)
    if recherche:
        connexions = connexions.filter(
            Q(utilisateur__username__icontains=recherche)
            | Q(identifiant_saisi__icontains=recherche)
            | Q(adresse_ip__icontains=recherche)
        )

    depuis_24h = timezone.now() - timedelta(hours=24)
    page = paginate(request, connexions, 40)

    return render(
        request,
        "accounts/connexion_history.html",
        {
            "page_obj": page,
            "connexions": page.object_list,
            "resultat_filter": resultat_filter,
            "search_term": recherche,
            "resultat_choices": ConnexionLog.Resultat.choices,
            "base_querystring": querystring_without(request, "page"),
            "stats": {
                "total": page.paginator.count,
                "echecs_24h": ConnexionLog.objects.filter(
                    resultat=ConnexionLog.Resultat.ECHEC,
                    date__gte=depuis_24h,
                ).count(),
                "connexions_24h": ConnexionLog.objects.filter(
                    resultat=ConnexionLog.Resultat.SUCCES,
                    date__gte=depuis_24h,
                ).count(),
            },
        },
    )


# --------------------------------------------------------------- services


@capability_required(can_manage_accounts)
def service_list(request):
    services = Service.objects.annotate(
        membres_total=Count("membres", distinct=True)
    ).order_by("nom")

    return render(
        request,
        "accounts/service_list.html",
        {"services": services, "total": services.count()},
    )


@capability_required(can_manage_accounts)
def service_create(request):
    if request.method == "POST":
        form = ServiceForm(request.POST)
        if form.is_valid():
            service = form.save()
            log_activity(request.user, "Création d'un service", "Comptes", service.nom)
            messages.success(request, f"Le service {service.nom} a été créé.")
            return redirect("accounts:service_list")
    else:
        form = ServiceForm()

    return render(
        request,
        "accounts/service_form.html",
        {"form": form, "title": "Nouveau service", "is_creation": True},
    )


@capability_required(can_manage_accounts)
def service_edit(request, pk):
    service = get_object_or_404(Service, pk=pk)
    if request.method == "POST":
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            service = form.save()
            log_activity(request.user, "Mise à jour d'un service", "Comptes", service.nom)
            messages.success(request, "Le service a été mis à jour.")
            return redirect("accounts:service_list")
    else:
        form = ServiceForm(instance=service)

    return render(
        request,
        "accounts/service_form.html",
        {
            "form": form,
            "service": service,
            "title": f"Modifier {service.nom}",
            "is_creation": False,
        },
    )


@capability_required(can_manage_accounts)
@require_POST
def service_delete(request, pk):
    service = get_object_or_404(Service, pk=pk)
    membres = service.membres.count()
    if membres:
        messages.error(
            request,
            f"{membres} agent(s) sont rattachés au service {service.nom} : "
            "désactivez-le plutôt que de le supprimer, pour ne pas orpheliner les fiches.",
        )
        return redirect("accounts:service_list")

    nom = service.nom
    service.delete()
    log_activity(request.user, "Suppression d'un service", "Comptes", nom)
    messages.success(request, f"Le service {nom} a été supprimé.")
    return redirect("accounts:service_list")


# ------------------------------------------------- mots de passe et etat


@capability_required(can_manage_accounts)
@require_POST
def user_password_reset(request, pk):
    """Attribue un mot de passe provisoire, affiché une seule fois."""
    user = get_object_or_404(User, pk=pk)

    provisoire = secrets.token_urlsafe(9)
    user.set_password(provisoire)
    user.save(update_fields=["password"])

    profile = user.profil
    profile.doit_changer_mot_de_passe = True
    profile.save(update_fields=["doit_changer_mot_de_passe"])

    # Le mot de passe provisoire vaut aussi pour la messagerie : l'agent n'a
    # qu'un seul secret a retenir, et il le changera une seule fois.
    avertissement = synchroniser_sans_bloquer(user, mot_de_passe=provisoire)

    log_activity(request.user, "Réinitialisation d'un mot de passe", "Comptes", user.username)
    messages.success(
        request,
        f"Mot de passe provisoire de {user.username} : {provisoire} — "
        "notez-le maintenant, il ne sera plus affiché. Il vaut pour l'intranet "
        "comme pour la messagerie. L'agent devra le changer à sa prochaine "
        "connexion.",
    )
    if avertissement:
        messages.warning(request, avertissement)
    return redirect(safe_next_url(request, request.POST.get("next"), "accounts:user_list"))


@capability_required(can_manage_accounts)
@require_POST
def user_toggle_active(request, pk):
    """Active ou desactive un compte, sans le supprimer."""
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect(safe_next_url(request, request.POST.get("next"), "accounts:user_list"))

    profile = user.profil
    profile.actif = not profile.actif
    profile.save()

    # Le point qui compte le jour ou quelqu'un quitte la direction : fermer
    # l'intranet sans fermer la messagerie ne ferme rien.
    avertissement = synchroniser_sans_bloquer(user)

    etat = "réactivé" if profile.actif else "désactivé"
    log_activity(request.user, f"Compte {etat}", "Comptes", user.username)
    messages.success(
        request,
        f"Le compte {user.username} a été {etat}, messagerie comprise.",
    )
    if avertissement:
        messages.warning(request, avertissement)
    return redirect(safe_next_url(request, request.POST.get("next"), "accounts:user_list"))


@login_required
def password_change(request):
    """Changement de son propre mot de passe.

    Egalement la seule page accessible a un agent dont le mot de passe vient
    d'etre reinitialise par l'administrateur.
    """
    profile = getattr(request.user, "profil", None)
    impose = bool(profile and profile.doit_changer_mot_de_passe)

    if request.method == "POST":
        form = MotDePasseChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            # Conserve la session active : sans cela, changer son mot de passe
            # deconnecte immediatement l'agent qui vient de le faire.
            update_session_auth_hash(request, form.user)
            if profile and profile.doit_changer_mot_de_passe:
                profile.doit_changer_mot_de_passe = False
                profile.save(update_fields=["doit_changer_mot_de_passe"])
            # Seul moment ou l'intranet connait le nouveau mot de passe en
            # clair : c'est ici, et nulle part ailleurs, qu'il peut le porter
            # a la messagerie pour que l'agent n'en retienne qu'un.
            avertissement = synchroniser_sans_bloquer(
                request.user, mot_de_passe=form.cleaned_data.get("new_password1")
            )
            log_activity(request.user, "Changement de mot de passe", "Comptes", request.user.username)
            if avertissement:
                # Ici l'avertissement vaut erreur : les deux mots de passe ont
                # diverge. L'agent doit savoir qu'il entrera dans la messagerie
                # avec l'ancien, sans quoi il conclura qu'elle est en panne.
                messages.error(
                    request,
                    "Votre mot de passe d'intranet a été modifié, mais celui de la "
                    "messagerie n'a pas pu l'être : elle attend donc toujours votre "
                    "ancien mot de passe. Signalez-le à l'ingénieur informatique.",
                )
            else:
                messages.success(
                    request,
                    "Votre mot de passe a été modifié. Il vaut aussi pour la messagerie.",
                )
            return redirect("dashboard:home")
    else:
        form = MotDePasseChangeForm(user=request.user)

    return render(
        request,
        "accounts/password_change.html",
        {"form": form, "impose": impose},
    )


@capability_required(can_manage_accounts)
def user_create(request):
    if request.method == "POST":
        user_form = AgentUserCreationForm(request.POST, prefix="user")
        profile_form = UserProfileForm(request.POST, prefix="profile")
        if user_form.is_valid() and profile_form.is_valid():
            user = user_form.save()
            profile = user.profil
            for field, value in profile_form.cleaned_data.items():
                setattr(profile, field, value)
            profile.save()
            # Le compte de messagerie nait avec le compte agent, avec le meme
            # identifiant et le meme mot de passe. Rien a creer a la main dans
            # Nextcloud, et donc rien qui puisse diverger.
            avertissement = synchroniser_sans_bloquer(
                user, mot_de_passe=user_form.cleaned_data.get("password1")
            )
            log_activity(request.user, "Création d'un compte agent", "Comptes", user.username)
            messages.success(
                request,
                "Le compte agent a été créé, avec son accès à la messagerie.",
            )
            if avertissement:
                messages.warning(request, avertissement)
            return redirect("accounts:user_list")
    else:
        user_form = AgentUserCreationForm(prefix="user")
        profile_form = UserProfileForm(prefix="profile")

    return render(
        request,
        "accounts/user_form.html",
        {
            "title": "Nouveau compte agent",
            "user_form": user_form,
            "profile_form": profile_form,
            "is_creation": True,
        },
    )


@capability_required(can_manage_accounts)
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    profile = user.profil

    if request.method == "POST":
        user_form = AgentUserUpdateForm(request.POST, instance=user, prefix="user")
        profile_form = UserProfileForm(request.POST, instance=profile, prefix="profile")
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            # Nom, adresse et service changent aussi dans la messagerie : un
            # agent muté doit quitter les conversations de son ancien service.
            avertissement = synchroniser_sans_bloquer(user)
            log_activity(request.user, "Mise à jour d'un compte agent", "Comptes", user.username)
            messages.success(request, "Le compte agent a été mis à jour.")
            if avertissement:
                messages.warning(request, avertissement)
            return redirect("accounts:user_list")
    else:
        user_form = AgentUserUpdateForm(instance=user, prefix="user")
        profile_form = UserProfileForm(instance=profile, prefix="profile")

    return render(
        request,
        "accounts/user_form.html",
        {
            "title": f"Modifier {user.get_full_name() or user.username}",
            "user_form": user_form,
            "profile_form": profile_form,
            "is_creation": False,
            "agent_user": user,
        },
    )


@capability_required(can_manage_accounts)
@require_POST
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        return redirect(safe_next_url(request, request.POST.get("next"), "accounts:user_list"))

    username = user.username
    # La messagerie est fermee avant la suppression, tant que le compte existe
    # encore : le compte Nextcloud est desactive et non supprime, pour que les
    # conversations gardent trace de qui a ecrit quoi.
    avertissement = desactiver_acces_messagerie(username)
    user.delete()
    log_activity(request.user, "Suppression d'un compte agent", "Comptes", username)
    messages.success(request, "Le compte agent a été supprimé et sa messagerie fermée.")
    if avertissement:
        messages.warning(request, avertissement)
    return redirect(safe_next_url(request, request.POST.get("next"), "accounts:user_list"))

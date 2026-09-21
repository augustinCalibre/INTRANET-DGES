"""Capacites d'acces de l'intranet DGES.

Les vues, formulaires et selectors ne testent jamais un role directement :
ils appellent une capacite. Le nom de la fonction dit ce qui est autorise,
pas qui l'est. La correspondance role -> capacite vit dans
`accounts.constants`, ce qui permet de reorganiser les roles sans revenir
sur les 17 gabarits ni sur les vues.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from accounts.constants import (
    ROLE_ADMINISTRATEUR,
    ROLE_AGENT_ETUDE,
    ROLE_COURRIER,
    ROLE_DIRECTEUR_GENERAL,
    ROLE_SECRETARIAT,
    ROLE_SECRETARIAT_ADJOINT,
    ROLES_ACCES_BORDEREAUX,
    ROLES_ACCES_COURRIERS,
    ROLES_ACCES_DIPLOMES,
    ROLES_AFFECTATION_LIBRE,
    ROLES_BORDEREAUX,
    ROLES_CLASSEMENT,
    ROLES_CONSULTATION_COMPTES,
    ROLES_COURRIER,
    ROLES_DIPLOMES,
    ROLES_DOCUMENTS,
    ROLES_FICHE_DG,
    ROLES_GESTION_COMPTES,
    ROLES_PLANNING,
    ROLES_SAUVEGARDE,
    ROLES_TRANSMISSION_DG,
    ROLES_VALIDATION_DG,
    ROLES_VISITEURS,
    ROLES_VUE_GLOBALE,
)


# ------------------------------------------------------------------ socle


def get_user_role(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if user.is_superuser:
        return ROLE_ADMINISTRATEUR
    profile = getattr(user, "profil", None)
    return getattr(profile, "role", None)


def user_has_role(user, *roles):
    if not getattr(user, "is_authenticated", False):
        return False
    return user.is_superuser or get_user_role(user) in roles


def _in(user, roles):
    """Le compte porte-t-il l'un des roles de cet ensemble ?"""
    if not getattr(user, "is_authenticated", False):
        return False
    return user.is_superuser or get_user_role(user) in roles


def role_required(*roles):
    """Restreint une vue a une liste de roles explicites."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if user_has_role(request.user, *roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied

        return _wrapped_view

    return decorator


def capability_required(capability):
    """Restreint une vue a une capacite, par exemple `can_manage_visitors`.

    A preferer a `role_required` : la vue exprime ce qu'elle fait, pas la
    liste des roles autorises a un instant donne.
    """

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if capability(request.user):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied

        return _wrapped_view

    return decorator


# ------------------------------------------------------------- identites


def is_admin_user(user):
    """Ingenieur informatique : administration complete de la plateforme."""
    return _in(user, {ROLE_ADMINISTRATEUR})


def is_dg_user(user):
    return _in(user, {ROLE_DIRECTEUR_GENERAL})


def is_secretariat_user(user):
    return _in(user, {ROLE_SECRETARIAT})


def is_secretariat_adjoint_user(user):
    return _in(user, {ROLE_SECRETARIAT_ADJOINT})


def is_courrier_user(user):
    return _in(user, {ROLE_COURRIER})


def is_agent_etude_user(user):
    return _in(user, {ROLE_AGENT_ETUDE})


# -------------------------------------------------------------- capacites


def can_view_all_activity(user):
    """Voir l'activite de toute la direction, tous services confondus."""
    return _in(user, ROLES_VUE_GLOBALE)


def can_manage_visitors(user):
    """Enregistrer un visiteur, corriger sa fiche, acter sa sortie."""
    return _in(user, ROLES_VISITEURS)


def can_manage_courriers(user):
    """Receptionner et traiter le courrier entrant."""
    return _in(user, ROLES_COURRIER)


def can_manage_documents(user):
    """Deposer et classer une piece dans la gestion documentaire."""
    return _in(user, ROLES_DOCUMENTS)


def can_transmit_to_dg(user):
    """Apposer le visa du Secretariat et transmettre au Directeur General.

    Point de passage unique : ni le service courrier ni l'agent d'etude ne
    saisissent directement le bureau du DG.
    """
    return _in(user, ROLES_TRANSMISSION_DG)


def can_validate_as_dg(user):
    """Viser, signer ou retourner pour correction."""
    return _in(user, ROLES_VALIDATION_DG)


def can_manage_diplomas(user):
    """Receptionner un lot, y inserer les diplomes, les verifier, valider."""
    return _in(user, ROLES_DIPLOMES)


def can_close_courrier(user):
    """Classer un courrier dont la suite a ete donnee.

    Le Directeur General et le Secretariat cloturent l'affaire au meme titre
    que le service courrier : c'est souvent l'un d'eux qui constate que la
    suite a ete donnee.
    """
    return _in(user, ROLES_CLASSEMENT)


def can_record_dg_decision(user):
    """Renseigner la fiche d'analyse : imputations, instructions, observations.

    Ouverte au Directeur General et au Secretariat : le DG annote souvent la
    fiche papier au moment de la remise, et le Secretariat reporte ensuite.
    L'application enregistre qui a saisi, et si c'etait pour le compte du DG.
    """
    return _in(user, ROLES_FICHE_DG)


def can_access_courriers(user):
    """Consulter le registre du courrier.

    Plus large que `can_manage_courriers` : le Secretariat vise, le DG
    traite, sans pour autant enregistrer les arrivees.
    """
    return _in(user, ROLES_ACCES_COURRIERS)


def can_access_diplomas(user):
    """Consulter le registre des lots.

    Plus large que `can_manage_diplomas` : le Secretariat consulte pour
    transmettre, le DG pour signer, sans toucher au contenu des lots.
    """
    return _in(user, ROLES_ACCES_DIPLOMES)


def can_manage_bordereaux(user):
    """Enregistrer un bordereau et saisir ses dates de signature."""
    return _in(user, ROLES_BORDEREAUX)


def can_access_bordereaux(user):
    """Consulter le suivi trimestriel des bordereaux.

    Plus large que `can_manage_bordereaux` : le Directeur General lit le
    tableau pour savoir ou en sont les dossiers, sans saisir les signatures.
    """
    return _in(user, ROLES_ACCES_BORDEREAUX)


def can_manage_all_meetings(user):
    """Tenir le planning du Directeur General et les reunions de direction.

    Tout agent peut par ailleurs organiser ses propres reunions : cette
    capacite concerne la gestion de celles des autres.
    """
    return _in(user, ROLES_PLANNING)


def can_assign_to_anyone(user):
    """Affecter une tache a un autre agent ou a un autre service."""
    return _in(user, ROLES_AFFECTATION_LIBRE)


def can_manage_accounts(user):
    """Creer les comptes et distribuer les acces."""
    return _in(user, ROLES_GESTION_COMPTES)


def can_view_accounts(user):
    """Consulter l'annuaire des comptes sans pouvoir le modifier."""
    return _in(user, ROLES_CONSULTATION_COMPTES)


def can_manage_backups(user):
    """Declencher une sauvegarde et restaurer une archive anterieure."""
    return _in(user, ROLES_SAUVEGARDE)


# ------------------------------------------------------ compatibilite

# `can_manage_meetings` reste expose : les gabarits et le contexte global
# l'utilisent. Il sera scinde en phase 4, quand chaque agent pourra gerer
# et partager ses propres reunions.
def can_manage_meetings(user):
    return can_manage_all_meetings(user)

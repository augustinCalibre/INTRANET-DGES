"""Synchronisation des roles applicatifs avec les groupes Django."""

from django.contrib.auth.models import Group, Permission

from .constants import (
    GROUP_PERMISSIONS,
    ROLE_ADMINISTRATEUR,
    ROLE_GROUP_NAMES,
)


def _permissions_for_role(role):
    if role == ROLE_ADMINISTRATEUR:
        return Permission.objects.all()

    permission_ids = []
    for app_label, codename in GROUP_PERMISSIONS.get(role, []):
        permission_ids.extend(
            Permission.objects.filter(
                content_type__app_label=app_label,
                codename=codename,
            ).values_list("id", flat=True)
        )
    return Permission.objects.filter(id__in=permission_ids)


def ensure_role_groups():
    """Cree les groupes manquants et realigne leurs permissions."""
    for role, group_name in ROLE_GROUP_NAMES.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.set(_permissions_for_role(role))


def sync_user_role_group(user):
    """Aligne groupe, statut equipe et activation sur le profil de l'agent."""
    profile = getattr(user, "profil", None)
    if profile is None:
        return

    ensure_role_groups()

    group_name = ROLE_GROUP_NAMES.get(profile.role)
    group = Group.objects.filter(name=group_name).first() if group_name else None
    user.groups.set([group] if group else [])

    # Seul l'administrateur accede a l'administration Django.
    desired_staff = user.is_superuser or profile.role == ROLE_ADMINISTRATEUR
    desired_active = profile.actif

    fields_to_update = []
    if user.is_staff != desired_staff:
        user.is_staff = desired_staff
        fields_to_update.append("is_staff")
    if user.is_active != desired_active:
        user.is_active = desired_active
        fields_to_update.append("is_active")
    if fields_to_update:
        user.save(update_fields=fields_to_update)


def sync_all_users():
    """Realigne tous les comptes. Utile apres un changement de matrice.

    Cree aussi le profil manquant des comptes anterieurs au mecanisme de
    profils, par exemple un superutilisateur cree en ligne de commande.
    """
    from django.contrib.auth.models import User

    from .models import UserProfile

    ensure_role_groups()
    total = 0
    for user in User.objects.all():
        profile, _ = UserProfile.objects.get_or_create(utilisateur=user)
        # Amorce le cache de la relation inverse : evite une requete de plus
        # et rend le profil visible meme s'il vient d'etre cree.
        user.profil = profile
        sync_user_role_group(user)
        total += 1
    return total

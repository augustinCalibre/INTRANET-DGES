from django.contrib.auth.models import User
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .access import ensure_role_groups, sync_all_users, sync_user_role_group
from .models import UserProfile


@receiver(post_migrate, dispatch_uid="accounts.setup_roles")
def setup_roles_and_permissions(sender=None, **kwargs):
    # post_migrate est emis une fois par application : on ne travaille que
    # pour la notre, sinon tout tournerait une dizaine de fois par migration.
    app_config = kwargs.get("app_config")
    if app_config is not None and app_config.label != "accounts":
        return

    ensure_role_groups()
    # Realigne les comptes existants. Indispensable apres un changement de
    # la matrice de droits : sans cela un agent garderait ses anciens groupes
    # jusqu'a la prochaine modification de son profil.
    sync_all_users()


@receiver(post_save, sender=User)
def create_profile_for_user(sender, instance, created, **kwargs):
    # Un profil est cree a l'inscription du compte, et seulement la. Les
    # comptes anterieurs depourvus de profil sont rattrapes par
    # `sync_all_users`, declenche a chaque migration.
    if created:
        UserProfile.objects.create(utilisateur=instance)


@receiver(post_save, sender=UserProfile)
def sync_profile_role(sender, instance, **kwargs):
    sync_user_role_group(instance.utilisateur)

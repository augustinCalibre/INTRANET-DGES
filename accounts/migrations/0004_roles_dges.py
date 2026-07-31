"""Passage au modele de roles de la DGES.

Les anciens roles « Responsable service » et « Agent simple » sont reportes
sur le role neutre « Agent ». Les groupes de l'ancien modele sont supprimes :
`ensure_role_groups`, declenche par post_migrate, recree l'ensemble correct
et `sync_all_users` reaffecte chaque compte a son nouveau groupe.
"""

from django.db import migrations, models

LEGACY_ROLE_MAP = {
    "agent_simple": "agent",
    "responsable_service": "agent",
}

OBSOLETE_GROUP_NAMES = [
    "DGES - Directeur General",
    "DGES - Secretariat",
    "DGES - Responsable service",
    "DGES - Agent simple",
    "DGES - Service Courrier",
]

ROLE_CHOICES = [
    ("directeur_general", "Directeur Général"),
    ("administrateur", "Administrateur"),
    ("secretariat", "Secrétariat"),
    ("secretariat_adjoint", "Secrétariat adjoint"),
    ("courrier", "Service courrier"),
    ("agent_etude", "Agent d'étude / vérificateur"),
    ("agent", "Agent"),
]


def migrer_roles(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    for ancien, nouveau in LEGACY_ROLE_MAP.items():
        UserProfile.objects.filter(role=ancien).update(role=nouveau)

    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=OBSOLETE_GROUP_NAMES).delete()


def revenir_aux_anciens_roles(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    # Les deux anciens roles ayant fusionne, le retour se fait sur le plus
    # restrictif des deux.
    UserProfile.objects.filter(
        role__in=["agent", "secretariat_adjoint", "courrier", "agent_etude"]
    ).update(role="agent_simple")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_alter_userprofile_role"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(choices=ROLE_CHOICES, default="agent", max_length=32),
        ),
        migrations.RunPython(migrer_roles, revenir_aux_anciens_roles),
    ]

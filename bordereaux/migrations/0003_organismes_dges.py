"""Referentiel des organismes suivis par la DGES.

La liste est installee par migration et non saisie a la main : elle doit
exister a l'identique sur chaque deploiement, sans qu'on ait a la ressaisir
apres une restauration ou sur une nouvelle installation.

L'operation est idempotente. Un organisme deja present est reconnu a son nom
et n'est pas duplique ; seul son sigle est aligne sur celui retenu ici, ce
qui permet de corriger une abreviation sans toucher aux bordereaux qui lui
sont deja rattaches.

Tous ces libelles ne designent pas des etablissements : le suivi compte aussi
des directions, un programme et des natures de dossier. C'est voulu — dans le
tableau trimestriel, ce sont des lignes au meme titre que les universites,
parce que leurs bordereaux suivent le meme circuit de signature.
"""

from django.db import migrations

ORGANISMES = [
    # Universites et etablissements
    ("UFHB", "Université Félix Houphouët-Boigny"),
    ("UNA", "Université Nangui Abrogoua"),
    ("ENS", "École Normale Supérieure"),
    ("UVCI", "Université Virtuelle de Côte d'Ivoire"),
    ("USP", "Université de San-Pédro"),
    ("UBK", "Université de Bondoukou"),
    ("INP-HB", "Institut National Polytechnique Félix Houphouët-Boigny"),
    ("UAO", "Université Alassane Ouattara"),
    ("UPGC", "Université Péléforo Gon Coulibaly"),
    ("UJLoG", "Université Jean Lorougnon Guédé"),
    ("UMAN", "Université de Man"),
    ("UIGB", "Université Internationale de Grand-Bassam"),
    ("GPE", "Groupe des Établissements Privés"),
    # Programme
    ("PDU", "Programme de Décentralisation des Universités"),
    # Directions et organismes rattaches
    ("DESUP", "Direction de l'Enseignement Supérieur"),
    ("DEXCO", "Direction des Examens et Concours"),
    (
        "OIPDES",
        "Observatoire de l'Insertion Professionnelle des Diplômés de "
        "l'Enseignement Supérieur",
    ),
    # Natures de dossier suivies au meme titre qu'un organisme
    ("BTS – DAF", "Brevet de Technicien Supérieur / Direction Administrative et Financière"),
    ("Prise en charge", "Dossier / activité de prise en charge"),
]


def installer_les_organismes(apps, schema_editor):
    Organisme = apps.get_model("bordereaux", "Organisme")

    for sigle, nom in ORGANISMES:
        organisme, cree = Organisme.objects.get_or_create(
            nom=nom,
            defaults={"sigle": sigle, "actif": True},
        )
        if not cree and organisme.sigle != sigle:
            organisme.sigle = sigle
            organisme.save(update_fields=["sigle", "updated_at"])


def retirer_les_organismes(apps, schema_editor):
    """Ne retire que ceux restes vierges de tout bordereau.

    Revenir en arriere ne doit pas emporter un suivi deja commence : un
    organisme auquel des bordereaux sont rattaches est laisse en place.
    """
    Organisme = apps.get_model("bordereaux", "Organisme")
    Organisme.objects.filter(
        nom__in=[nom for _, nom in ORGANISMES],
        bordereaux__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("bordereaux", "0002_bordereau_joint_et_numero_facultatif"),
    ]

    operations = [
        migrations.RunPython(installer_les_organismes, retirer_les_organismes),
    ]

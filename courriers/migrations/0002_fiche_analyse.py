"""Fiche d'analyse du courrier.

Reprend le formulaire papier de la DGES : numero d'arrivee, grille
d'imputations et liste d'instructions. La grille et les instructions sont
amorcees avec les libelles du formulaire ; leur rattachement a un service ou a
un compte revient a l'administrateur, depuis le panneau d'acces.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Grille d'imputation du formulaire papier, colonne par colonne.
IMPUTATIONS = [
    ("SERVICE ADMINISTRATIF", "SERVICE ADMINISTRATIF"),
    ("SERVICE ADMINISTRATIF", "M. N'GAZA"),
    ("SERVICE ADMINISTRATIF", "Mme BAILLY"),
    ("SERVICE DIPLOME", "SERVICE DIPLOME"),
    ("SERVICE DIPLOME", "Mme KONAN"),
    ("SERVICE DIPLOME", "M. DOSSO"),
    ("SUIVI-EVALUATION", "SUIVI-EVALUATION"),
    ("SUIVI-EVALUATION", "SERVICE-COMM"),
    ("DESUP", "DESUP"),
    ("DESUP", "SECRETARIAT"),
    ("DOUVAG", "DOUVAG"),
    ("DOUVAG", "C.T"),
]

INSTRUCTIONS = [
    "Urgence",
    "Pour Suite à Donner",
    "A Suivre",
    "Me Représenter",
    "Soit-Transmis",
    "M'en Parler",
    "Pour Attribution",
    "Assister à L'audience",
    "Large Diffusion",
    "Pour Information",
    "A classer",
    "Participer au Séminaire",
]


def amorcer(apps, schema_editor):
    Imputation = apps.get_model("courriers", "Imputation")
    InstructionCourrier = apps.get_model("courriers", "InstructionCourrier")

    for index, (categorie, libelle) in enumerate(IMPUTATIONS):
        Imputation.objects.get_or_create(
            libelle=libelle,
            categorie=categorie,
            defaults={"ordre": index * 10, "actif": True},
        )

    for index, libelle in enumerate(INSTRUCTIONS):
        InstructionCourrier.objects.get_or_create(
            libelle=libelle,
            defaults={"ordre": index * 10, "actif": True},
        )


def vider(apps, schema_editor):
    apps.get_model("courriers", "Imputation").objects.all().delete()
    apps.get_model("courriers", "InstructionCourrier").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("courriers", "0001_initial"),
        ("accounts", "0005_userprofile_doit_changer_mot_de_passe"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InstructionCourrier",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("libelle", models.CharField(max_length=120, unique=True)),
                ("ordre", models.PositiveIntegerField(default=0)),
                ("actif", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Instruction",
                "verbose_name_plural": "Instructions",
                "ordering": ["ordre", "libelle"],
            },
        ),
        migrations.CreateModel(
            name="Imputation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "libelle",
                    models.CharField(
                        help_text="Texte imprimé sur la fiche, tel qu'il figure sur le formulaire papier.",
                        max_length=120,
                    ),
                ),
                (
                    "categorie",
                    models.CharField(
                        blank=True,
                        help_text="Colonne de la grille, par exemple « SERVICE ADMINISTRATIF ».",
                        max_length=120,
                    ),
                ),
                ("ordre", models.PositiveIntegerField(default=0)),
                ("actif", models.BooleanField(default=True)),
                (
                    "agent",
                    models.ForeignKey(
                        blank=True,
                        help_text="Agent visé, lorsque la case désigne une personne.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="imputations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "service",
                    models.ForeignKey(
                        blank=True,
                        help_text="Service visé par cette case.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="imputations",
                        to="accounts.service",
                    ),
                ),
            ],
            options={
                "verbose_name": "Imputation",
                "verbose_name_plural": "Imputations",
                "ordering": ["ordre", "libelle"],
            },
        ),
        migrations.AddField(
            model_name="courrier",
            name="numero_arrivee",
            field=models.CharField(
                blank=True,
                help_text="Numéro « COURRIER ARRIVÉE » porté sur la pièce à la réception.",
                max_length=60,
            ),
        ),
        migrations.AddField(
            model_name="courrier",
            name="autres_instructions",
            field=models.TextField(
                blank=True,
                help_text="Rubrique « AUTRES » de la fiche d'analyse.",
                verbose_name="Autres instructions",
            ),
        ),
        migrations.AddField(
            model_name="courrier",
            name="date_fiche",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="courrier",
            name="fiche_pour_le_compte_du_dg",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Vrai lorsque le secrétariat reporte une fiche annotée sur papier "
                    "par le Directeur Général."
                ),
            ),
        ),
        migrations.AddField(
            model_name="courrier",
            name="fiche_saisie_par",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="fiches_saisies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="courrier",
            name="imputations",
            field=models.ManyToManyField(
                blank=True,
                related_name="courriers",
                to="courriers.imputation",
                verbose_name="Imputations",
            ),
        ),
        migrations.AddField(
            model_name="courrier",
            name="instructions",
            field=models.ManyToManyField(
                blank=True,
                related_name="courriers",
                to="courriers.instructioncourrier",
                verbose_name="Instructions",
            ),
        ),
        migrations.AlterField(
            model_name="courrier",
            name="instruction_dg",
            field=models.TextField(
                blank=True,
                help_text="Observations portées par le Directeur Général sur la fiche d'analyse.",
            ),
        ),
        migrations.RunPython(amorcer, vider),
    ]

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import courriers.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0004_roles_dges"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Courrier",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "reference",
                    models.CharField(
                        blank=True,
                        help_text="Laisser vide pour une attribution automatique.",
                        max_length=40,
                        unique=True,
                    ),
                ),
                (
                    "sens",
                    models.CharField(
                        choices=[("entrant", "Entrant"), ("sortant", "Sortant")],
                        default="entrant",
                        max_length=20,
                    ),
                ),
                ("objet", models.CharField(max_length=255)),
                ("expediteur", models.CharField(max_length=180)),
                ("date_reception", models.DateField(default=django.utils.timezone.localdate)),
                (
                    "date_courrier",
                    models.DateField(
                        blank=True,
                        help_text="Date portée sur le courrier, si elle diffère de la réception.",
                        null=True,
                    ),
                ),
                (
                    "priorite",
                    models.CharField(
                        choices=[("normale", "Normale"), ("urgente", "Urgente")],
                        default="normale",
                        max_length=20,
                    ),
                ),
                (
                    "fichier",
                    models.FileField(blank=True, upload_to=courriers.models.courrier_upload_path),
                ),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("recu", "Reçu"),
                            ("en_traitement", "En traitement"),
                            ("transmis_secretariat", "Transmis au secrétariat"),
                            ("transmis_dg", "Transmis au DG"),
                            ("vise_dg", "Visé par le DG"),
                            ("retourne", "Retourné pour suite à donner"),
                            ("classe", "Classé"),
                        ],
                        default="recu",
                        max_length=25,
                    ),
                ),
                ("observation", models.TextField(blank=True)),
                (
                    "instruction_dg",
                    models.TextField(
                        blank=True,
                        help_text="Annotation portée par le Directeur Général lors du visa.",
                    ),
                ),
                ("date_transmission_secretariat", models.DateTimeField(blank=True, null=True)),
                ("date_transmission_dg", models.DateTimeField(blank=True, null=True)),
                ("date_visa", models.DateTimeField(blank=True, null=True)),
                ("date_retour", models.DateTimeField(blank=True, null=True)),
                ("date_classement", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "cree_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="courriers_crees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "destinataire_service",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="courriers",
                        to="accounts.service",
                    ),
                ),
                (
                    "receptionne_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="courriers_receptionnes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "transmis_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="courriers_transmis",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "vise_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="courriers_vises",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Courrier",
                "verbose_name_plural": "Courriers",
                "ordering": ["-date_reception", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CourrierHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("action", models.CharField(max_length=180)),
                ("ancien_statut", models.CharField(blank=True, max_length=25)),
                ("nouveau_statut", models.CharField(blank=True, max_length=25)),
                ("commentaire", models.TextField(blank=True)),
                ("date", models.DateTimeField(auto_now_add=True)),
                (
                    "courrier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="historiques",
                        to="courriers.courrier",
                    ),
                ),
                (
                    "utilisateur",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="courrier_histories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Historique de courrier",
                "verbose_name_plural": "Historiques de courrier",
                "ordering": ["-date"],
            },
        ),
        migrations.AddIndex(
            model_name="courrier",
            index=models.Index(fields=["statut"], name="cour_statut_idx"),
        ),
        migrations.AddIndex(
            model_name="courrier",
            index=models.Index(fields=["-date_reception"], name="cour_reception_idx"),
        ),
        migrations.AddIndex(
            model_name="courrier",
            index=models.Index(fields=["expediteur"], name="cour_expediteur_idx"),
        ),
    ]

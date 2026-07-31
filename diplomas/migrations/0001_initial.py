import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0003_alter_userprofile_role"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LotDiplomes",
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
                ("etablissement", models.CharField(max_length=180)),
                ("date_arrivee", models.DateField(default=django.utils.timezone.localdate)),
                ("nombre_annonce", models.PositiveIntegerField(default=0)),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("recu", "Reçu"),
                            ("en_verification", "En vérification"),
                            ("conforme", "Conforme"),
                            ("transmis_dg", "Transmis au DG"),
                            ("signe", "Signé"),
                            ("retourne", "Retourné au service"),
                            ("remis", "Remis"),
                            ("archive", "Archivé"),
                        ],
                        default="recu",
                        max_length=20,
                    ),
                ),
                ("observation", models.TextField(blank=True)),
                ("date_transmission_dg", models.DateTimeField(blank=True, null=True)),
                ("date_signature", models.DateTimeField(blank=True, null=True)),
                ("date_retour", models.DateTimeField(blank=True, null=True)),
                ("date_remise", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "agent_receptionnaire",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lots_receptionnes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "cree_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lots_crees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "service_concerne",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lots_diplomes",
                        to="accounts.service",
                    ),
                ),
                (
                    "signe_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lots_signes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "transmis_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lots_transmis",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Lot de diplômes",
                "verbose_name_plural": "Lots de diplômes",
                "ordering": ["-date_arrivee", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Diplome",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nom_beneficiaire", models.CharField(max_length=180)),
                ("numero_diplome", models.CharField(max_length=80)),
                ("filiere", models.CharField(blank=True, max_length=150)),
                ("etablissement", models.CharField(blank=True, max_length=180)),
                ("annee_academique", models.CharField(blank=True, max_length=20)),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("a_verifier", "À vérifier"),
                            ("conforme", "Conforme"),
                            ("non_conforme", "Non conforme"),
                            ("transmis_dg", "Transmis au DG"),
                            ("signe", "Signé"),
                            ("retire", "Retiré"),
                            ("archive", "Archivé"),
                        ],
                        default="a_verifier",
                        max_length=20,
                    ),
                ),
                (
                    "anomalie",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("manquant", "Diplôme manquant"),
                            ("erreur_nom", "Erreur sur le nom"),
                            ("reference_incorrecte", "Référence incorrecte"),
                            ("piece_non_conforme", "Pièce non conforme"),
                            ("autre", "Autre anomalie"),
                        ],
                        max_length=30,
                    ),
                ),
                ("observations", models.TextField(blank=True)),
                ("date_retrait", models.DateTimeField(blank=True, null=True)),
                (
                    "retire_par",
                    models.CharField(
                        blank=True,
                        help_text="Personne ayant retiré le diplôme.",
                        max_length=180,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "lot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="diplomes",
                        to="diplomas.lotdiplomes",
                    ),
                ),
            ],
            options={
                "verbose_name": "Diplôme",
                "verbose_name_plural": "Diplômes",
                "ordering": ["nom_beneficiaire", "numero_diplome"],
            },
        ),
        migrations.CreateModel(
            name="LotHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("action", models.CharField(max_length=180)),
                ("ancien_statut", models.CharField(blank=True, max_length=20)),
                ("nouveau_statut", models.CharField(blank=True, max_length=20)),
                ("commentaire", models.TextField(blank=True)),
                ("date", models.DateTimeField(auto_now_add=True)),
                (
                    "lot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="historiques",
                        to="diplomas.lotdiplomes",
                    ),
                ),
                (
                    "utilisateur",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="lot_histories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Historique de lot",
                "verbose_name_plural": "Historiques de lot",
                "ordering": ["-date"],
            },
        ),
        migrations.CreateModel(
            name="DiplomeHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("action", models.CharField(max_length=180)),
                ("ancien_statut", models.CharField(blank=True, max_length=20)),
                ("nouveau_statut", models.CharField(blank=True, max_length=20)),
                ("commentaire", models.TextField(blank=True)),
                ("date", models.DateTimeField(auto_now_add=True)),
                (
                    "diplome",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="historiques",
                        to="diplomas.diplome",
                    ),
                ),
                (
                    "utilisateur",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="diplome_histories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Historique de diplôme",
                "verbose_name_plural": "Historiques de diplôme",
                "ordering": ["-date"],
            },
        ),
        migrations.AddIndex(
            model_name="lotdiplomes",
            index=models.Index(fields=["statut"], name="dip_lot_statut_idx"),
        ),
        migrations.AddIndex(
            model_name="lotdiplomes",
            index=models.Index(fields=["-date_arrivee"], name="dip_lot_arrivee_idx"),
        ),
        migrations.AddIndex(
            model_name="diplome",
            index=models.Index(fields=["numero_diplome"], name="dip_numero_idx"),
        ),
        migrations.AddIndex(
            model_name="diplome",
            index=models.Index(fields=["nom_beneficiaire"], name="dip_nom_idx"),
        ),
        migrations.AddIndex(
            model_name="diplome",
            index=models.Index(fields=["statut"], name="dip_statut_idx"),
        ),
        migrations.AddConstraint(
            model_name="diplome",
            constraint=models.UniqueConstraint(
                fields=("lot", "numero_diplome"), name="unique_numero_diplome_par_lot"
            ),
        ),
    ]

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_notification_courrier"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConnexionLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "identifiant_saisi",
                    models.CharField(
                        blank=True,
                        help_text="Identifiant tapé, conservé même quand le compte n'existe pas.",
                        max_length=150,
                    ),
                ),
                (
                    "resultat",
                    models.CharField(
                        choices=[
                            ("succes", "Connexion réussie"),
                            ("echec", "Échec de connexion"),
                            ("deconnexion", "Déconnexion"),
                        ],
                        default="succes",
                        max_length=20,
                    ),
                ),
                ("adresse_ip", models.GenericIPAddressField(blank=True, null=True)),
                (
                    "poste",
                    models.CharField(
                        blank=True,
                        help_text="Navigateur et système déclarés par le poste.",
                        max_length=255,
                    ),
                ),
                ("date", models.DateTimeField(auto_now_add=True)),
                (
                    "utilisateur",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="connexions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Connexion",
                "verbose_name_plural": "Historique des connexions",
                "ordering": ["-date"],
            },
        ),
        migrations.AddIndex(
            model_name="connexionlog",
            index=models.Index(fields=["-date"], name="conn_date_idx"),
        ),
        migrations.AddIndex(
            model_name="connexionlog",
            index=models.Index(fields=["resultat"], name="conn_resultat_idx"),
        ),
    ]

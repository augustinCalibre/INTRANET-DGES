"""Repertoire des correspondants externes, et symetrie des deux sens.

Jusqu'ici, un courrier avait un `expediteur` en texte libre et un service
destinataire interne — la lecture du courrier entrant. Le sortant se lit en
miroir : il part d'un service de la DGES vers un organisme exterieur.

D'ou deux champs nouveaux, et le repertoire qui les accompagne. Ce repertoire
se remplit a l'usage plutot que d'etre administre : un nom saisi pour la
premiere fois cree sa fiche. La colonne `nom_normalise` — accents retires,
casse ignoree — porte l'unicite reelle, faute de quoi « Universite FHB » et
« Université F.H.B. » deviendraient deux organismes distincts.

`expediteur` devient facultatif : un courrier sortant n'en a pas. Les
courriers deja enregistres gardent le leur, et les proprietes `provenance` et
`destinataire` savent le lire.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_userprofile_doit_changer_mot_de_passe"),
        ("courriers", "0005_courrier_nature"),
    ]

    operations = [
        migrations.CreateModel(
            name="CorrespondantExterne",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nom", models.CharField(max_length=200, unique=True)),
                (
                    "nom_normalise",
                    models.CharField(editable=False, max_length=200, unique=True),
                ),
                ("actif", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Correspondant externe",
                "verbose_name_plural": "Correspondants externes",
                "ordering": ["nom"],
            },
        ),
        migrations.AddField(
            model_name="courrier",
            name="service_emetteur",
            field=models.ForeignKey(
                blank=True,
                help_text="Service de la DGES à l'origine d'un courrier sortant.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="courriers_emis",
                to="accounts.service",
                verbose_name="Service émetteur",
            ),
        ),
        migrations.AddField(
            model_name="courrier",
            name="destinataire_externe",
            field=models.ForeignKey(
                blank=True,
                help_text="Organisme extérieur destinataire d'un courrier sortant.",
                null=True,
                # PROTECT et non SET_NULL : supprimer un correspondant qui a
                # reçu du courrier effacerait la trace de l'envoi. On oblige a
                # traiter les courriers d'abord.
                on_delete=django.db.models.deletion.PROTECT,
                related_name="courriers",
                to="courriers.correspondantexterne",
                verbose_name="Destinataire",
            ),
        ),
        migrations.AlterField(
            model_name="courrier",
            name="destinataire_service",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="courriers",
                to="accounts.service",
                verbose_name="Service destinataire",
            ),
        ),
        migrations.AlterField(
            model_name="courrier",
            name="expediteur",
            field=models.CharField(
                blank=True,
                help_text="Organisme ou personne à l'origine d'un courrier entrant.",
                max_length=180,
                verbose_name="Expéditeur",
            ),
        ),
    ]

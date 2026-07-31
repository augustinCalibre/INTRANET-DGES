"""Les salles deviennent une entite reservable.

Le champ texte `salle` est remplace par une cle etrangere vers `Salle`, ce qui
permet de detecter les conflits d'occupation. Les libelles deja saisis sont
convertis en salles, aucune reunion ne perd son lieu.
"""

import django.db.models.deletion
from django.db import migrations, models


def creer_salles_depuis_les_libelles(apps, schema_editor):
    Meeting = apps.get_model("meetings", "Meeting")
    Salle = apps.get_model("meetings", "Salle")

    for libelle in (
        Meeting.objects.exclude(salle="").values_list("salle", flat=True).distinct()
    ):
        nom = libelle.strip()
        if not nom:
            continue
        salle, _ = Salle.objects.get_or_create(nom=nom, defaults={"actif": True})
        Meeting.objects.filter(salle=libelle).update(salle_reservee=salle)


def revenir_aux_libelles(apps, schema_editor):
    Meeting = apps.get_model("meetings", "Meeting")
    for meeting in Meeting.objects.select_related("salle_reservee"):
        if meeting.salle_reservee_id:
            meeting.salle = meeting.salle_reservee.nom
            meeting.save(update_fields=["salle"])


class Migration(migrations.Migration):

    # Non atomique volontairement. Sur PostgreSQL, ajouter une cle etrangere a
    # une table qui contient des lignes met en attente la validation de la
    # contrainte ; toute operation de schema suivante dans la meme transaction
    # est alors refusee (« pending trigger events »). En decoupant les
    # transactions, chaque etape se valide avant la suivante.
    atomic = False

    dependencies = [
        ("meetings", "0002_meeting_rappel_15_envoye_at_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Salle",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nom", models.CharField(max_length=120, unique=True)),
                ("localisation", models.CharField(blank=True, max_length=180)),
                (
                    "capacite",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Nombre de places. 0 si l'information n'est pas connue.",
                    ),
                ),
                (
                    "equipements",
                    models.CharField(
                        blank=True,
                        help_text="Projecteur, visioconférence, tableau…",
                        max_length=255,
                    ),
                ),
                ("actif", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Salle",
                "verbose_name_plural": "Salles",
                "ordering": ["nom"],
            },
        ),
        migrations.AddField(
            model_name="meeting",
            name="duree_minutes",
            field=models.PositiveIntegerField(default=60, help_text="Durée prévue, en minutes."),
        ),
        migrations.AddField(
            model_name="meeting",
            name="salle_reservee",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reunions",
                to="meetings.salle",
            ),
        ),
        migrations.RunPython(creer_salles_depuis_les_libelles, revenir_aux_libelles),
        # La suppression de l'ancien champ texte est reportee dans la migration
        # suivante : PostgreSQL refuse un ALTER TABLE dans la meme transaction
        # qu'un UPDATE sur la meme table (« pending trigger events »).
    ]

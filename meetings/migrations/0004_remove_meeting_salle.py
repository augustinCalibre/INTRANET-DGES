"""Retrait de l'ancien champ texte `salle`.

Operation isolee dans sa propre migration, donc dans sa propre transaction :
PostgreSQL refuse un ALTER TABLE dans la transaction qui vient de modifier les
lignes de la meme table.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("meetings", "0003_salles_et_duree"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="meeting",
            name="salle",
        ),
    ]

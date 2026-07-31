"""Lien entre un courrier et les taches ouvertes pour y donner suite.

L'agent impute ne traite pas le courrier lui-meme : il traite la tache qui en
decoule. L'avancement de cette tache remonte dans l'historique du courrier,
ce qui permet au secretariat et au Directeur General de savoir quand l'affaire
peut etre classee.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courriers", "0003_imputations_reelles"),
        ("tasks", "0002_task_partage_avec"),
    ]

    operations = [
        migrations.AddField(
            model_name="courrier",
            name="taches",
            field=models.ManyToManyField(
                blank=True,
                related_name="courriers_origine",
                to="tasks.task",
                verbose_name="Tâches de suivi",
            ),
        ),
    ]

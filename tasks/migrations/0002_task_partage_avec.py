from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="partage_avec",
            field=models.ManyToManyField(
                blank=True,
                help_text="Agents qui peuvent consulter et faire avancer cette tâche.",
                related_name="tasks_partagees",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Partagée avec",
            ),
        ),
    ]

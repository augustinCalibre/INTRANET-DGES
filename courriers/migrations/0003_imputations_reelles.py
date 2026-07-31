"""Les imputations visent les services et les comptes reels.

La premiere version reprenait la liste de libelles du formulaire papier, qu'il
aurait fallu maintenir a la main a chaque mouvement de personnel. La grille est
desormais construite a partir des services actifs et de leurs agents : creer un
service ou un compte suffit a le faire apparaitre sur la fiche.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courriers", "0002_fiche_analyse"),
        ("accounts", "0005_userprofile_doit_changer_mot_de_passe"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="courrier",
            name="services_imputes",
            field=models.ManyToManyField(
                blank=True,
                related_name="courriers_imputes",
                to="accounts.service",
                verbose_name="Services imputés",
            ),
        ),
        migrations.AddField(
            model_name="courrier",
            name="agents_imputes",
            field=models.ManyToManyField(
                blank=True,
                related_name="courriers_imputes",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Agents imputés",
            ),
        ),
        migrations.RemoveField(
            model_name="courrier",
            name="imputations",
        ),
        migrations.RemoveField(
            model_name="imputation",
            name="agent",
        ),
        migrations.RemoveField(
            model_name="imputation",
            name="service",
        ),
        migrations.DeleteModel(
            name="Imputation",
        ),
    ]

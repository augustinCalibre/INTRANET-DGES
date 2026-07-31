from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_roles_dges"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="doit_changer_mot_de_passe",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Actif après une réinitialisation par l'administrateur : l'agent est "
                    "contraint de choisir un nouveau mot de passe à sa prochaine connexion."
                ),
                verbose_name="Doit changer son mot de passe",
            ),
        ),
    ]

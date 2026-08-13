"""La liste des diplomes, jointe au lot telle qu'elle arrive.

Les etablissements remettent une liste sur papier ou en PDF, jamais un
tableur. L'import Excel qui existait jusqu'ici demandait un format que
personne ne fournissait : il est remplace par le depot de la piece elle-meme.

Elle n'est pas depouillee ligne a ligne. La verification consiste a relever
les diplomes non conformes, la difference avec le nombre annonce etant
conforme d'office — depouiller deux cents lignes pour n'en signaler que trois
n'a jamais eu de sens. Le fichier reste la piece de reference en cas de
contestation.
"""

import diplomas.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("diplomas", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="lotdiplomes",
            name="fichier_liste",
            field=models.FileField(
                blank=True,
                upload_to=diplomas.models.liste_lot_upload_path,
                verbose_name="Liste des diplômes",
            ),
        ),
    ]

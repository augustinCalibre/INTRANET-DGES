"""Nature du document, distincte du sens.

Le sens dit si le courrier entre ou s'il sort, et fonde les registres arrivee
et depart. La nature dit de quel document il s'agit. Un ordre de mission peut
entrer comme sortir : melanger les deux notions dans un seul champ aurait fait
perdre l'un des deux renseignements.

Les courriers deja enregistres prennent « Courrier simple », qui est ce qu'ils
sont.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courriers", "0004_courrier_taches"),
    ]

    operations = [
        migrations.AddField(
            model_name="courrier",
            name="nature",
            field=models.CharField(
                choices=[
                    ("courrier", "Courrier simple"),
                    ("autorisation", "Autorisation"),
                    ("note", "Note"),
                    ("ordre_mission", "Ordre de mission"),
                ],
                default="courrier",
                max_length=20,
                verbose_name="Nature du document",
            ),
        ),
    ]

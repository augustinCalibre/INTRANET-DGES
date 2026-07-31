from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_notification"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="type_notification",
            field=models.CharField(
                choices=[
                    ("info", "Information"),
                    ("meeting", "Reunion"),
                    ("diplome", "Lot de diplomes"),
                ],
                default="info",
                max_length=20,
            ),
        ),
    ]

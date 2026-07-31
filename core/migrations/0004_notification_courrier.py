from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_alter_notification_type_notification"),
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
                    ("courrier", "Courrier"),
                ],
                default="info",
                max_length=20,
            ),
        ),
    ]

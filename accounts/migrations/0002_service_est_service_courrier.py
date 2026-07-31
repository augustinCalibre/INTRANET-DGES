from django.db import migrations, models


def mark_existing_courrier_services(apps, schema_editor):
    Service = apps.get_model("accounts", "Service")
    Service.objects.filter(nom__in=["Service Courrier", "Courrier", "Service du Courrier"]).update(
        est_service_courrier=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="est_service_courrier",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(mark_existing_courrier_services, migrations.RunPython.noop),
    ]

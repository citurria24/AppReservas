import uuid
from django.db import migrations, models


def populate_cancellation_tokens(apps, schema_editor):
    Reservation = apps.get_model("salons", "Reservation")
    for reservation in Reservation.objects.filter(cancellation_token__isnull=True).iterator():
        reservation.cancellation_token = uuid.uuid4()
        reservation.save(update_fields=["cancellation_token"])


class Migration(migrations.Migration):
    dependencies = [("salons", "0002_guestverification_workschedule_schedulebreak_and_more")]

    operations = [
        migrations.AddField(
            model_name="hairsalon",
            name="cancellation_notice_hours",
            field=models.PositiveSmallIntegerField(default=24, verbose_name="anticipación mínima para cancelar"),
        ),
        migrations.AddField(
            model_name="reservation",
            name="cancellation_token",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(populate_cancellation_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="reservation",
            name="cancellation_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]

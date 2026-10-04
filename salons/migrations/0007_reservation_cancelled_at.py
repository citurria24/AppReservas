from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("salons", "0006_reservationreschedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="cancelada"),
        ),
        migrations.AddIndex(
            model_name="reservation",
            index=models.Index(
                fields=["salon", "status", "cancelled_at"],
                name="reservation_cancel_policy_idx",
            ),
        ),
    ]

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("salons", "0010_salon_operational_policies"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bookinglimitexception",
            name="reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="limit_exceptions",
                to="salons.reservation",
                verbose_name="reserva que utilizó la excepción",
            ),
        ),
    ]

import uuid

from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from salons.tests import test_agenda


class SimplifiedStatusMigrationTests(TransactionTestCase):
    create_reservation = classmethod(test_agenda.AgendaPermissionTests.create_reservation.__func__)

    def test_conversion_preserves_reservations_audit_and_overlap_protection(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('salons', '0008_reservationstatuschange_and_more')])
        old_apps = executor.loader.project_state([('salons', '0008_reservationstatuschange_and_more')]).apps
        try:
            test_agenda.AgendaPermissionTests.setUpTestData.__func__(type(self))
            old_reservations = old_apps.get_model('salons', 'Reservation')
            old_history = old_apps.get_model('salons', 'ReservationStatusChange')
            old_reservations.objects.filter(pk=self.own_reservation.pk).update(status='in_progress')
            old_reservations.objects.filter(pk=self.colleague_reservation.pk).update(status='completed')
            old_reservations.objects.filter(pk=self.foreign_reservation.pk).update(status='cancelled_salon')
            original = old_reservations.objects.filter(pk=self.own_reservation.pk).values().get()
            original['status'] = 'confirmed'
            history = old_history.objects.create(reservation_id=self.own_reservation.pk, previous_status='confirmed', new_status='in_progress', changed_by_id=self.owner.pk)
            executor = MigrationExecutor(connection)
            executor.migrate([('salons', '0009_simplify_reservation_status')])
            apps = executor.loader.project_state([('salons', '0009_simplify_reservation_status')]).apps
            reservations = apps.get_model('salons', 'Reservation')
            audit = apps.get_model('salons', 'ReservationStatusChange')
            self.assertEqual(reservations.objects.filter(pk=self.own_reservation.pk).values().get(), original)
            self.assertEqual(reservations.objects.get(pk=self.colleague_reservation.pk).status, 'completed')
            self.assertEqual(reservations.objects.get(pk=self.foreign_reservation.pk).status, 'cancelled_salon')
            self.assertEqual(audit.objects.get(pk=history.pk).new_status, 'in_progress')
            conversion = audit.objects.exclude(pk=history.pk).get()
            self.assertEqual(conversion.previous_status, 'in_progress')
            self.assertEqual(conversion.new_status, 'confirmed')
            self.assertIsNone(conversion.changed_by_id)
            self.assertIsNotNone(conversion.created_at)
            duplicate = reservations.objects.get(pk=self.own_reservation.pk)
            duplicate.pk = None
            duplicate.cancellation_token = uuid.uuid4()
            with self.assertRaises(IntegrityError), transaction.atomic():
                duplicate.save()
            from importlib import import_module
            with transaction.atomic():
                import_module('salons.migrations.0009_simplify_reservation_status').restore_confirmed(apps, connection.schema_editor())
            self.assertEqual(audit.objects.count(), 2)
        finally:
            MigrationExecutor(connection).migrate([('salons', '0009_simplify_reservation_status')])

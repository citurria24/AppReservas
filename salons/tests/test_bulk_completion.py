import time as system_time
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from salons.models import Reservation, ReservationStatusChange
from salons.tests import test_agenda


class BulkCompletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_agenda.AgendaPermissionTests.setUpTestData.__func__(cls)
        cls.now = timezone.make_aware(datetime.combine(cls.day, time(12)))

    create_reservation = classmethod(test_agenda.AgendaPermissionTests.create_reservation.__func__)

    def setUp(self):
        patcher = patch('django.utils.timezone.now', return_value=self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def preview(self, user, branch='', day=None):
        self.client.force_login(user)
        return self.client.get(reverse('reservation-bulk-complete'), {'date': (day or self.day).isoformat(), 'branch': branch})

    def confirm(self, response):
        return self.client.post(reverse('reservation-bulk-complete'), {'token': response.context['token']})

    def test_owner_preview_and_confirm_per_reservation_audit(self):
        response = self.preview(self.owner)
        self.assertEqual(response.context['count'], 2)
        self.assertContains(response, 'Se marcarán 2 reservas como atendidas.')
        self.assertEqual(ReservationStatusChange.objects.count(), 0)
        self.assertEqual(self.confirm(response).status_code, 302)
        self.assertEqual(ReservationStatusChange.objects.count(), 2)
        for r in (self.own_reservation, self.colleague_reservation):
            r.refresh_from_db()
            self.assertEqual(r.status, 'completed')
            history = r.status_changes.get()
            self.assertEqual(history.previous_status, 'confirmed')
            self.assertEqual(history.new_status, 'completed')
            self.assertEqual(history.changed_by, self.owner)
            self.assertEqual(history.created_at, self.now)
        self.foreign_reservation.refresh_from_db()
        self.assertEqual(self.foreign_reservation.status, 'confirmed')

    def test_future_same_day_and_other_dates_excluded(self):
        future = self.create_reservation(self.salon, self.branch, self.service, self.professional, self.now + timedelta(hours=1), 'Futura')
        tomorrow = self.create_reservation(self.salon, self.branch, self.service, self.professional, self.now + timedelta(days=1), 'Manana')
        response = self.preview(self.owner)
        self.assertEqual(response.context['count'], 2)
        self.confirm(response)
        for r in (future, tomorrow):
            r.refresh_from_db()
            self.assertEqual(r.status, 'confirmed')

    def test_final_states_excluded(self):
        for status in ('completed', 'no_show', 'cancelled_client', 'cancelled_salon'):
            Reservation.objects.filter(salon=self.salon).update(status=status)
            response = self.preview(self.owner)
            self.assertEqual(response.context['count'], 0)
            self.assertContains(response, 'No hay reservas finalizadas pendientes de marcar como atendidas.')
            self.confirm(response)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_real_stored_duration_used_and_exact_end_excluded(self):
        Reservation.objects.filter(pk=self.own_reservation.pk).update(duration_minutes=180)
        Reservation.objects.filter(pk=self.colleague_reservation.pk).update(duration_minutes=120)
        response = self.preview(self.owner)
        self.assertEqual(response.context['count'], 0)

    def test_owner_selected_branch_only(self):
        Reservation.objects.filter(pk=self.colleague_reservation.pk).update(branch=self.other_branch_same_salon)
        response = self.preview(self.owner, self.branch.pk)
        self.assertEqual(response.context['count'], 1)
        result = self.confirm(response)
        self.assertIn('branch=' + str(self.branch.pk), result.url)
        self.colleague_reservation.refresh_from_db()
        self.assertEqual(self.colleague_reservation.status, 'confirmed')

    def test_admin_only_authorized_branches(self):
        Reservation.objects.filter(pk=self.colleague_reservation.pk).update(branch=self.other_branch_same_salon)
        response = self.preview(self.admin)
        self.assertEqual(response.context['count'], 1)
        self.confirm(response)
        self.colleague_reservation.refresh_from_db()
        self.assertEqual(self.colleague_reservation.status, 'confirmed')
        self.assertEqual(self.own_reservation.status_changes.get().changed_by, self.admin)

    def test_unauthorized_branch_and_cross_salon_filter_rejected(self):
        self.assertEqual(self.preview(self.admin, self.other_branch_same_salon.pk).status_code, 404)
        self.assertEqual(self.preview(self.owner, self.foreign_branch.pk).status_code, 404)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_hairdresser_no_bulk_permission_or_button(self):
        self.assertEqual(self.preview(self.hairdresser).status_code, 403)
        self.assertEqual(self.client.post(reverse('reservation-bulk-complete'), {'token': 'manual'}).status_code, 403)
        response = self.client.get(reverse('agenda'), {'date': self.day.isoformat()})
        self.assertNotContains(response, 'Marcar atendidas las finalizadas')

    def test_changed_state_between_preview_and_confirmation_excluded(self):
        response = self.preview(self.owner)
        Reservation.objects.filter(pk=self.own_reservation.pk).update(status='cancelled_client')
        self.confirm(response)
        self.assertEqual(ReservationStatusChange.objects.count(), 1)
        self.own_reservation.refresh_from_db()
        self.assertEqual(self.own_reservation.status, 'cancelled_client')

    def test_newly_finished_reservations_not_added_to_confirmed_lot(self):
        future = self.create_reservation(self.salon, self.branch, self.service, self.professional, self.now + timedelta(hours=1), 'Futura')
        response = self.preview(self.owner)
        with patch('django.utils.timezone.now', return_value=self.now + timedelta(hours=3)):
            self.confirm(response)
        future.refresh_from_db()
        self.assertEqual(future.status, 'confirmed')

    def test_repeat_confirmation_does_not_duplicate_audit(self):
        response = self.preview(self.owner)
        self.confirm(response)
        self.confirm(response)
        self.assertEqual(ReservationStatusChange.objects.count(), 2)

    def test_batch_rolls_back_if_audit_fails(self):
        response = self.preview(self.owner)
        original = ReservationStatusChange.objects.create
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise RuntimeError('audit failure')
            return original(**kwargs)
        with patch('salons.reservation_status.ReservationStatusChange.objects.create', side_effect=create):
            with self.assertRaises(RuntimeError):
                self.confirm(response)
        self.assertEqual(Reservation.objects.filter(salon=self.salon, status='confirmed').count(), 2)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_unsigned_expired_or_other_user_confirmation_rejected(self):
        response = self.preview(self.owner)
        self.assertEqual(self.client.post(reverse('reservation-bulk-complete'), {'token': response.context['token'] + 'x'}).status_code, 400)
        self.client.force_login(self.admin)
        self.assertEqual(self.confirm(response).status_code, 400)
        self.client.force_login(self.owner)
        with patch('django.core.signing.time.time', return_value=system_time.time() + 1000):
            self.assertEqual(self.confirm(response).status_code, 400)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_permissions_rechecked_after_preview(self):
        response = self.preview(self.admin)
        self.admin.salon_memberships.all().update(active=False)
        self.assertEqual(self.confirm(response).status_code, 403)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_invalid_date_is_rejected_without_changes(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('reservation-bulk-complete'), {'date': 'invalid'}).status_code, 400)
        self.assertFalse(ReservationStatusChange.objects.exists())

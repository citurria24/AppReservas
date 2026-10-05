import uuid
from datetime import time
from unittest.mock import patch

from django.contrib import admin
from django.test import RequestFactory
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from salons.booking import available_slots
from salons.models import (
    BranchService, ProfessionalService, Reservation, ReservationStatusChange,
    RewardProgram, WorkSchedule,
)
from salons.rescheduling import RescheduleError, reschedule_reservation
from salons.rewards import available_reward
from salons.tests import test_agenda


class ReservationStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_agenda.AgendaPermissionTests.setUpTestData.__func__(cls)

    create_reservation = classmethod(test_agenda.AgendaPermissionTests.create_reservation.__func__)

    def post(self, user, reservation, action, **extra):
        self.client.force_login(user)
        return self.client.post(reverse('reservation-status', args=[reservation.pk]), {'action': action}, **extra)

    def test_new_reservation_is_confirmed(self):
        self.assertEqual(self.own_reservation.status, Reservation.Status.CONFIRMED)

    def test_owner_all_operational_transitions_and_audit(self):
        S = Reservation.Status
        for previous, action, target in [
            (S.CONFIRMED, 'complete', S.COMPLETED),
            (S.CONFIRMED, 'no_show', S.NO_SHOW),
        ]:
            with self.subTest(previous=previous, action=action):
                Reservation.objects.filter(pk=self.own_reservation.pk).update(status=previous)
                before = timezone.now()
                response = self.post(self.owner, self.own_reservation, action)
                self.assertEqual(response.status_code, 302)
                self.own_reservation.refresh_from_db()
                self.assertEqual(self.own_reservation.status, target)
                history = self.own_reservation.status_changes.latest('pk')
                self.assertEqual(history.previous_status, previous)
                self.assertEqual(history.new_status, target)
                self.assertEqual(history.changed_by, self.owner)
                self.assertGreaterEqual(history.created_at, before)
        self.assertEqual(self.own_reservation.status_changes.count(), 2)

    def test_admin_authorized_branch(self):
        for action in ('complete', 'no_show'):
            Reservation.objects.filter(pk=self.own_reservation.pk).update(status='confirmed')
            self.assertEqual(self.post(self.admin, self.own_reservation, action).status_code, 302)

    def test_admin_unauthorized_branch(self):
        Reservation.objects.filter(pk=self.own_reservation.pk).update(branch=self.other_branch_same_salon)
        for action in ('complete', 'no_show', 'cancel'):
            self.assertEqual(self.post(self.admin, self.own_reservation, action).status_code, 404)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_hairdresser_own_reservation(self):
        for action in ('complete', 'no_show'):
            Reservation.objects.filter(pk=self.own_reservation.pk).update(status='confirmed')
            self.assertEqual(self.post(self.hairdresser, self.own_reservation, action).status_code, 302)

    def test_hairdresser_cannot_modify_colleague_or_foreign_reservation(self):
        for reservation in (self.colleague_reservation, self.foreign_reservation):
            for action in ('complete', 'no_show', 'cancel'):
                self.assertEqual(self.post(self.hairdresser, reservation, action).status_code, 404)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_cross_salon_ids_rejected(self):
        for action in ('complete', 'no_show', 'cancel'):
            self.assertEqual(self.post(self.other_owner, self.own_reservation, action).status_code, 404)
            self.assertEqual(self.post(self.owner, self.foreign_reservation, action).status_code, 404)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_final_states_reject_every_action_and_preserve_audit(self):
        for status in ('completed', 'no_show', 'cancelled_client', 'cancelled_salon'):
            Reservation.objects.filter(pk=self.own_reservation.pk).update(status=status)
            for action in ('complete', 'no_show', 'cancel', 'confirmed'):
                with self.subTest(status=status, action=action):
                    self.assertIn(self.post(self.owner, self.own_reservation, action).status_code, (403, 404))
                    self.own_reservation.refresh_from_db()
                    self.assertEqual(self.own_reservation.status, status)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_manual_unknown_action_and_get_rejected(self):
        for action in ('confirmed', 'start', 'in_progress'):
            self.assertEqual(self.post(self.owner, self.own_reservation, action).status_code, 404)
        self.assertEqual(self.client.get(reverse('reservation-status', args=[self.own_reservation.pk])).status_code, 404)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_only_completed_counts_for_rewards(self):
        RewardProgram.objects.create(salon=self.salon, active=True, services_required=1, period='monthly', discount_percent=15)
        for status in Reservation.Status.values:
            Reservation.objects.filter(pk=self.own_reservation.pk).update(status=status)
            reward = available_reward(self.salon, self.own_reservation.email, self.day)
            with self.subTest(status=status):
                if status == 'completed':
                    self.assertEqual(reward['attended'], 1)
                else:
                    self.assertIsNone(reward)

    def test_htmx_completion_hides_final_actions(self):
        response = self.post(self.owner, self.own_reservation, 'complete', HTTP_HX_REQUEST='true')
        self.assertContains(response, 'Atendida')
        self.assertNotContains(response, 'reservation-actions')

    def test_audit_failure_rolls_back_state_change(self):
        self.client.force_login(self.owner)
        with patch('salons.reservation_status.ReservationStatusChange.objects.create', side_effect=RuntimeError('audit failure')):
            with self.assertRaises(RuntimeError):
                self.post(self.owner, self.own_reservation, 'complete')
        self.own_reservation.refresh_from_db()
        self.assertEqual(self.own_reservation.status, 'confirmed')
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_local_cancellation_audit_and_timestamp(self):
        self.post(self.owner, self.own_reservation, 'cancel')
        self.own_reservation.refresh_from_db()
        self.assertIsNotNone(self.own_reservation.cancelled_at)
        self.assertEqual(self.own_reservation.status_changes.get().new_status, 'cancelled_salon')

    def test_confirmed_blocks_availability_and_database_overlap(self):
        BranchService.objects.create(branch=self.branch, service=self.service, duration_minutes=30)
        ProfessionalService.objects.create(professional=self.professional, service=self.service)
        WorkSchedule.objects.create(professional=self.professional, branch=self.branch, weekday=self.day.weekday(), starts_at=time(9), ends_at=time(18))
        for status in ('confirmed', 'completed', 'no_show', 'cancelled_client', 'cancelled_salon'):
            Reservation.objects.filter(pk=self.own_reservation.pk).update(status=status)
            slots = available_slots(salon=self.salon, branch=self.branch, service=self.service, professional=self.professional, day=self.day)
            with self.subTest(status=status):
                self.assertEqual(self.own_reservation.starts_at in slots, status != 'confirmed')
        Reservation.objects.filter(pk=self.own_reservation.pk).update(status='confirmed')
        for status in ('confirmed',):
            duplicate = Reservation.objects.get(pk=self.own_reservation.pk)
            duplicate.pk = None
            duplicate.status = status
            duplicate.cancellation_token = uuid.uuid4()
            with self.assertRaises(IntegrityError), transaction.atomic():
                Reservation.objects.bulk_create([duplicate])

    def test_client_cancellation_audit_once_without_internal_user(self):
        url = reverse('client-cancel', args=[self.salon.slug, self.own_reservation.cancellation_token])
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 200)
        history = self.own_reservation.status_changes.get()
        self.assertEqual(history.previous_status, 'confirmed')
        self.assertEqual(history.new_status, 'cancelled_client')
        self.assertIsNone(history.changed_by)
        self.assertIsNotNone(history.created_at)

    def test_audit_is_read_only_in_admin(self):
        request = RequestFactory().get('/')
        request.user = self.owner
        audit_admin = admin.site._registry[ReservationStatusChange]
        self.assertFalse(audit_admin.has_add_permission(request))
        self.assertFalse(audit_admin.has_change_permission(request))
        self.assertFalse(audit_admin.has_delete_permission(request))

    def test_all_non_confirmed_states_reject_internal_and_client_rescheduling(self):
        self.client.force_login(self.owner)
        for status in ('completed', 'no_show', 'cancelled_client', 'cancelled_salon'):
            Reservation.objects.filter(pk=self.own_reservation.pk).update(status=status)
            self.own_reservation.refresh_from_db()
            with self.subTest(status=status):
                self.assertFalse(self.own_reservation.can_client_reschedule)
                self.assertEqual(self.client.post(reverse('reservation-reschedule', args=[self.own_reservation.pk]), {}).status_code, 403)
                response = self.client.post(reverse('client-reschedule', args=[self.salon.slug, self.own_reservation.cancellation_token]), {})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Esta reserva ya no se puede reprogramar')
                with self.assertRaises(RescheduleError):
                    reschedule_reservation(reservation=self.own_reservation, day=self.day, slot_value='', source='salon', changed_by=self.owner, request=None)
        self.assertFalse(self.own_reservation.reschedules.exists())

    def test_agenda_buttons_respect_role(self):
        url = reverse('agenda') + '?date=' + self.day.isoformat()
        self.client.force_login(self.hairdresser)
        response = self.client.get(url)
        self.assertNotContains(response, '>Iniciar<')
        self.assertContains(response, 'Marcar ausente')
        self.assertNotContains(response, 'Reprogramar')
        self.assertNotContains(response, 'Cancelar desde el local')
        self.assertNotContains(response, 'Cliente colega')
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertContains(response, 'Reprogramar')
        self.assertContains(response, 'Cancelar desde el local')

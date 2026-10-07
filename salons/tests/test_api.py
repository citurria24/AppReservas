from datetime import datetime, time
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from salons.models import Reservation, ReservationStatusChange, Membership
from salons.tests import test_agenda
from salons.tests.test_agenda import after_start


class ReactApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_agenda.AgendaPermissionTests.setUpTestData.__func__(cls)

    create_reservation = classmethod(test_agenda.AgendaPermissionTests.create_reservation.__func__)

    def login(self, user=None):
        self.client.force_login(user or self.owner)

    def agenda(self, **filters):
        return self.client.get(reverse('api-agenda'), {'date': self.day.isoformat(), **filters})

    def action(self, reservation, action):
        return self.client.post(reverse('api-reservation-action', args=[reservation.pk]), {'action': action}, content_type='application/json')

    def test_anonymous_get_returns_json_401_without_redirect(self):
        for name, args in [('api-me', []), ('api-agenda', []), ('api-statistics', [self.salon.slug])]:
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response['Content-Type'], 'application/json')
            self.assertNotIn('Location', response)

    def test_me_exposes_session_context_minimal_permissions_and_csrf(self):
        self.login()
        response = self.client.get(reverse('api-me'))
        data = response.json()
        self.assertEqual(data['role'], 'owner')
        self.assertEqual(data['salon']['slug'], self.salon.slug)
        self.assertTrue(data['permissions']['statistics'])
        self.assertTrue(data['permissions']['bulk_complete'])
        self.assertEqual(len(data['branches']), 2)
        self.assertIn('csrftoken', response.cookies)
        self.assertTrue(data['csrf_token'])
        self.assertNotIn('password', data)
        self.assertNotIn('email', data)

    def test_me_other_roles_and_cross_salon_selection(self):
        for user, role, bulk in [(self.admin, 'admin', True), (self.hairdresser, 'hairdresser', False)]:
            self.login(user)
            data = self.client.get(reverse('api-me')).json()
            self.assertEqual(data['role'], role)
            self.assertEqual(data['permissions']['bulk_complete'], bulk)
            self.assertFalse(data['permissions']['statistics'])
            self.assertEqual([b['id'] for b in data['branches']], [self.branch.pk])
            self.assertEqual(self.client.get(reverse('api-me'), {'salon': self.other_salon.slug}).status_code, 404)

    def test_owner_agenda_actions_and_cross_tenant_isolation(self):
        self.login()
        with after_start(self.own_reservation):
            data = self.agenda().json()
        self.assertEqual(data['summary']['total'], 2)
        row = next(r for r in data['reservations'] if r['id'] == self.own_reservation.pk)
        self.assertEqual(set(row['allowed_actions']), {'mark_attended', 'mark_absent', 'reschedule', 'cancel_local'})
        self.assertEqual(row['reschedule_url'], reverse('reservation-reschedule', args=[self.own_reservation.pk]))
        self.assertEqual(row['start_time'], '10:00')
        self.assertEqual(row['client'], 'Cliente propio Demo')
        self.assertNotIn(self.foreign_reservation.pk, [r['id'] for r in data['reservations']])

    def test_admin_branch_filter_and_manipulated_branch(self):
        Reservation.objects.filter(pk=self.colleague_reservation.pk).update(branch=self.other_branch_same_salon)
        self.login(self.admin)
        self.assertEqual([r['id'] for r in self.agenda().json()['reservations']], [self.own_reservation.pk])
        self.assertEqual(self.agenda(branch=self.other_branch_same_salon.pk).status_code, 404)
        self.assertEqual(self.agenda(branch=self.foreign_branch.pk).status_code, 404)
        self.assertEqual(self.action(self.colleague_reservation, 'mark_attended').status_code, 404)

    def test_hairdresser_only_own_reservation_and_actions(self):
        self.login(self.hairdresser)
        with after_start(self.own_reservation):
            data = self.agenda().json()
        self.assertEqual(len(data['reservations']), 1)
        self.assertEqual(set(data['reservations'][0]['allowed_actions']), {'mark_attended', 'mark_absent'})
        self.assertFalse(data['can_bulk_complete'])
        self.assertEqual(self.action(self.colleague_reservation, 'mark_attended').status_code, 404)
        self.assertEqual(self.action(self.own_reservation, 'cancel_local').status_code, 403)

    def test_final_states_have_no_actions(self):
        self.login()
        for status in ('completed', 'no_show', 'cancelled_client', 'cancelled_salon'):
            Reservation.objects.filter(pk=self.own_reservation.pk).update(status=status)
            row = next(r for r in self.agenda().json()['reservations'] if r['id'] == self.own_reservation.pk)
            self.assertEqual(row['allowed_actions'], [])
            self.assertIsNone(row['reschedule_url'])
            self.assertEqual(self.action(self.own_reservation, 'mark_attended').status_code, 403)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_attended_absent_and_local_cancel_reuse_audit(self):
        self.login()
        for action, status in [('mark_attended', 'completed'), ('mark_absent', 'no_show'), ('cancel_local', 'cancelled_salon')]:
            Reservation.objects.filter(pk=self.own_reservation.pk).update(status='confirmed', cancelled_at=None)
            with after_start(self.own_reservation):
                self.assertEqual(self.action(self.own_reservation, action).status_code, 200)
            self.own_reservation.refresh_from_db()
            self.assertEqual(self.own_reservation.status, status)
            self.assertEqual(self.own_reservation.status_changes.latest('pk').changed_by, self.owner)
            self.assertEqual(self.own_reservation.cancelled_at is not None, action == 'cancel_local')
        self.assertEqual(ReservationStatusChange.objects.count(), 3)

    def test_cross_salon_action_ids_rejected_without_audit(self):
        self.login(self.other_owner)
        for action in ('mark_attended', 'mark_absent', 'cancel_local'):
            self.assertEqual(self.action(self.own_reservation, action).status_code, 404)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_revoked_membership_applies_with_existing_session(self):
        self.login(self.admin)
        Membership.objects.filter(user=self.admin).update(active=False)
        self.assertEqual(self.agenda().json()['reservations'], [])
        self.assertEqual(self.action(self.own_reservation, 'mark_attended').status_code, 404)
        self.assertFalse(self.client.get(reverse('api-me')).json()['permissions']['bulk_complete'])

    def test_bulk_preview_then_execute_with_individual_audit(self):
        self.login()
        now = timezone.make_aware(datetime.combine(self.day, time(12)))
        with patch('django.utils.timezone.now', return_value=now):
            response = self.client.post(reverse('api-bulk-preview'), {'date': self.day.isoformat(), 'branch': self.branch.pk}, content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['count'], 2)
            self.assertFalse(ReservationStatusChange.objects.exists())
            result = self.client.post(reverse('api-bulk-execute'), {'token': response.json()['token']}, content_type='application/json')
            self.assertEqual(result.json()['count'], 2)
        self.assertEqual(ReservationStatusChange.objects.count(), 2)
        self.foreign_reservation.refresh_from_db()
        self.assertEqual(self.foreign_reservation.status, 'confirmed')

    def test_admin_bulk_scope_and_hairdresser_denied(self):
        Reservation.objects.filter(pk=self.colleague_reservation.pk).update(branch=self.other_branch_same_salon)
        self.login(self.admin)
        now = timezone.make_aware(datetime.combine(self.day, time(12)))
        with patch('django.utils.timezone.now', return_value=now):
            response = self.client.post(reverse('api-bulk-preview'), {'date': self.day.isoformat()}, content_type='application/json')
            self.assertEqual(response.json()['count'], 1)
            result = self.client.post(reverse('api-bulk-execute'), {'token': response.json()['token']}, content_type='application/json')
            self.assertEqual(result.json()['count'], 1)
        self.login(self.hairdresser)
        for name in ('api-bulk-preview', 'api-bulk-execute'):
            self.assertEqual(self.client.post(reverse(name), {'date': self.day.isoformat(), 'token': 'manual'}, content_type='application/json').status_code, 403)

    def test_tampered_bulk_confirmation_rejected(self):
        self.login()
        self.assertEqual(self.client.post(reverse('api-bulk-execute'), {'token': 'manual'}, content_type='application/json').status_code, 400)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_owner_statistics_filters_distribution_and_excel(self):
        self.login()
        Reservation.objects.filter(pk=self.own_reservation.pk).update(status='completed', reward_discount_percent=15)
        filters = {'year': self.day.year, 'month': self.day.month, 'branch': self.branch.pk}
        response = self.client.get(reverse('api-statistics', args=[self.salon.slug]), filters)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['summary']['total'], 2)
        self.assertEqual(data['summary']['attended'], 1)
        self.assertEqual(data['summary']['discounts'], 1)
        self.assertEqual(sum(r['count'] for r in data['distribution']), 2)
        self.assertEqual({r['status'] for r in data['distribution']}, {'confirmed', 'completed'})
        self.assertEqual(len(data['by_branch']), 1)
        excel = self.client.get(data['export_url'], filters)
        self.assertEqual(excel.status_code, 200)
        self.assertEqual(excel['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_statistics_403_other_roles_404_other_salon_and_bad_filters(self):
        url = reverse('api-statistics', args=[self.salon.slug])
        for user in (self.admin, self.hairdresser):
            self.login(user)
            self.assertEqual(self.client.get(url).status_code, 403)
        self.login(self.other_owner)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.login()
        self.assertEqual(self.client.get(url, {'branch': self.foreign_branch.pk}).status_code, 400)
        self.assertEqual(self.client.get(url, {'month': 13}).status_code, 400)

    def test_invalid_json_action_and_dates_fail_without_audit(self):
        self.login()
        self.assertEqual(self.agenda(date='invalid').status_code, 400)
        url = reverse('api-reservation-action', args=[self.own_reservation.pk])
        for data in ('[]', '{broken', '{"action":"start"}'):
            self.assertEqual(self.client.post(url, data, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertFalse(ReservationStatusChange.objects.exists())

    @override_settings(CSRF_TRUSTED_ORIGINS=['http://localhost:5173'])
    def test_real_csrf_required_and_trusted_frontend_origin(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        token = client.get(reverse('api-me')).json()['csrf_token']
        url = reverse('api-reservation-action', args=[self.own_reservation.pk])
        denied = client.post(url, {'action': 'mark_attended'}, content_type='application/json')
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied['Content-Type'], 'application/json')
        self.assertFalse(ReservationStatusChange.objects.exists())
        with after_start(self.own_reservation):
            result = client.post(url, {'action': 'mark_attended'}, content_type='application/json', HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN='http://localhost:5173')
        self.assertEqual(result.status_code, 200)

    def test_django_template_pages_still_work(self):
        self.login()
        self.assertContains(self.client.get(reverse('agenda'), {'date': self.day.isoformat()}), 'Cliente propio')
        self.assertContains(self.client.get(reverse('statistics', args=[self.salon.slug])), 'Distribución de reservas')

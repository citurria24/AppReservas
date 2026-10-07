from datetime import datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from salons.access import MANAGE_OPERATIONAL_SETTINGS, membership_has_permission
from salons.booking import available_slots
from salons.cancellation_policy import active_cancellation_booking_block
from salons.models import (
    BookingLimitException,
    Branch,
    BranchService,
    HairSalon,
    Membership,
    MembershipBranch,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    Reservation,
    ReservationReschedule,
    Service,
    WorkSchedule,
)
from salons.rescheduling import slots_for_reservation


LOCAL_TZ = ZoneInfo(settings.TIME_ZONE)
EMAIL = "politicas@example.test"


def local(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=LOCAL_TZ)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class OperationalPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("ops-owner", "owner@ops.test", "test-pass-123")
        cls.admin = User.objects.create_user("ops-admin", "admin@ops.test", "test-pass-123")
        cls.hairdresser = User.objects.create_user("ops-hair", "hair@ops.test", "test-pass-123")
        cls.other_owner = User.objects.create_user("ops-other", "other@ops.test", "test-pass-123")

        cls.salon, cls.branch, cls.service, cls.professional = cls.build_salon("Norte", "norte", user=cls.hairdresser)
        cls.other_salon, cls.other_branch, cls.other_service, cls.other_professional = cls.build_salon("Sur", "sur")

        Membership.objects.create(salon=cls.salon, user=cls.owner, role=Membership.Role.OWNER)
        admin_membership = Membership.objects.create(salon=cls.salon, user=cls.admin, role=Membership.Role.ADMIN)
        MembershipBranch.objects.create(membership=admin_membership, branch=cls.branch)
        hair_membership = Membership.objects.create(salon=cls.salon, user=cls.hairdresser, role=Membership.Role.HAIRDRESSER)
        MembershipBranch.objects.create(membership=hair_membership, branch=cls.branch)
        Membership.objects.create(salon=cls.other_salon, user=cls.other_owner, role=Membership.Role.OWNER)

        # Two calendar days ahead keeps client-side rules valid at any hour.
        cls.day = timezone.localdate() + timedelta(days=2)

    @classmethod
    def build_salon(cls, name, slug, user=None):
        salon = HairSalon.objects.create(name=name, slug=slug)
        branch = Branch.objects.create(salon=salon, name="Centro", address="Principal 1", phone="2900 0000")
        service = Service.objects.create(salon=salon, name="Corte")
        professional = Professional.objects.create(salon=salon, display_name=f"Barbero {name}", user=user)
        ProfessionalBranch.objects.create(professional=professional, branch=branch)
        ProfessionalService.objects.create(professional=professional, service=service)
        BranchService.objects.create(branch=branch, service=service, duration_minutes=30)
        for weekday in range(7):
            WorkSchedule.objects.create(
                professional=professional, branch=branch, weekday=weekday, starts_at=time(9), ends_at=time(18),
            )
        return salon, branch, service, professional

    def set_policy(self, salon=None, **values):
        salon = salon or self.salon
        HairSalon.objects.filter(pk=salon.pk).update(**values)
        salon.refresh_from_db()
        return salon

    def slots(self, salon=None, day=None):
        salon = salon or self.salon
        if salon == self.salon:
            branch, service, professional = self.branch, self.service, self.professional
        else:
            branch, service, professional = self.other_branch, self.other_service, self.other_professional
        return available_slots(salon=salon, branch=branch, service=service, professional=professional, day=day or self.day)

    def create_reservation(self, starts_at, *, salon=None, email=EMAIL, status=Reservation.Status.CONFIRMED, cancelled_at=None):
        salon = salon or self.salon
        if salon == self.salon:
            branch, service, professional = self.branch, self.service, self.professional
        else:
            branch, service, professional = self.other_branch, self.other_service, self.other_professional
        return Reservation.objects.create(
            salon=salon, branch=branch, service=service, professional=professional,
            first_name="Cliente", last_name="Políticas", email=email, contact="099 000 000",
            starts_at=starts_at, ends_at=starts_at + timedelta(minutes=30), duration_minutes=30,
            status=status, cancelled_at=cancelled_at,
        )

    def verify_guest(self, salon=None):
        salon = salon or self.salon
        session = self.client.session
        session["verified_guest"] = {
            "salon_id": salon.id, "first_name": "Cliente", "last_name": "Políticas",
            "email": EMAIL, "contact": "099 000 000", "verified_at": timezone.now().isoformat(),
        }
        session.save()

    def post_booking(self, slot, day=None):
        return self.client.post(
            reverse("booking-create", args=[self.salon.slug]),
            {
                "branch": self.branch.id, "service": self.service.id, "professional": self.professional.id,
                "date": (day or self.day).isoformat(), "slot": slot.isoformat(), "notes": "",
            },
        )

    def policy_payload(self, **changes):
        return {
            "slot_interval_minutes": 15,
            "min_booking_notice_minutes": 0,
            "max_booking_horizon_days": 60,
            "max_daily_bookings_per_client": 5,
            "cancellation_notice_hours": 24,
            "cancellation_block_threshold": 3,
            "cancellation_block_window_days": 30,
            "cancellation_block_hours": 24,
        } | changes

    # Defaults y validación

    def test_defaults_reproduce_previous_behavior(self):
        salon = HairSalon.objects.create(name="Nueva", slug="nueva")
        self.assertEqual(salon.slot_interval_minutes, 15)
        self.assertEqual(salon.min_booking_notice_minutes, 0)
        self.assertEqual(salon.max_booking_horizon_days, 60)
        self.assertEqual(salon.max_daily_bookings_per_client, 5)
        self.assertEqual(salon.cancellation_notice_hours, 24)
        self.assertEqual(salon.cancellation_block_threshold, 3)
        self.assertEqual(salon.cancellation_block_window_days, 30)
        self.assertEqual(salon.cancellation_block_hours, 24)

    def test_model_validation_rejects_out_of_range_values(self):
        invalid = [
            {"slot_interval_minutes": 7},
            {"max_booking_horizon_days": 0},
            {"max_booking_horizon_days": 366},
            {"max_daily_bookings_per_client": 0},
            {"cancellation_block_threshold": 0},
            {"cancellation_block_window_days": 0},
            {"cancellation_block_hours": 0},
            {"min_booking_notice_minutes": 10081},
            {"min_booking_notice_minutes": 1440, "max_booking_horizon_days": 1},
        ]
        for values in invalid:
            with self.subTest(values=values):
                salon = HairSalon(name="Validar", slug="validar", **values)
                with self.assertRaises(ValidationError):
                    salon.full_clean()

    def test_database_constraint_protects_policies(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            HairSalon.objects.filter(pk=self.salon.pk).update(max_daily_bookings_per_client=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            HairSalon.objects.filter(pk=self.salon.pk).update(slot_interval_minutes=7)

    # Intervalo y duración

    def test_slot_interval_is_configurable_per_salon(self):
        self.set_policy(slot_interval_minutes=15)
        self.set_policy(self.other_salon, slot_interval_minutes=30)
        starts = [timezone.localtime(slot).time() for slot in self.slots()][:4]
        other_starts = [timezone.localtime(slot).time() for slot in self.slots(self.other_salon)][:4]
        self.assertEqual(starts, [time(9), time(9, 15), time(9, 30), time(9, 45)])
        self.assertEqual(other_starts, [time(9), time(9, 30), time(10), time(10, 30)])

    def test_service_duration_is_independent_from_slot_interval(self):
        self.set_policy(slot_interval_minutes=15)
        BranchService.objects.filter(branch=self.branch, service=self.service).update(duration_minutes=45)
        slots = [timezone.localtime(slot) for slot in self.slots()]
        self.assertEqual([slot.time() for slot in slots[:3]], [time(9), time(9, 15), time(9, 30)])
        # The last start leaves exactly 45 minutes before closing.
        self.assertEqual(slots[-1].time(), time(17, 15))

        self.set_policy(slot_interval_minutes=20)
        BranchService.objects.filter(branch=self.branch, service=self.service).update(duration_minutes=30)
        starts = [timezone.localtime(slot).time() for slot in self.slots()][:3]
        self.assertEqual(starts, [time(9), time(9, 20), time(9, 40)])

    # Anticipación mínima y horizonte

    def test_min_booking_notice_is_applied_to_availability(self):
        frozen_now = local(self.day, 10, 7)
        with patch("django.utils.timezone.now", return_value=frozen_now):
            self.assertEqual(timezone.localtime(self.slots()[0]).time(), time(10, 15))
            self.set_policy(min_booking_notice_minutes=60)
            self.assertEqual(timezone.localtime(self.slots()[0]).time(), time(11, 15))
            # Another salon keeps its own default.
            self.assertEqual(timezone.localtime(self.slots(self.other_salon)[0]).time(), time(10, 15))

    def test_max_booking_horizon_is_applied_to_availability(self):
        today = timezone.localdate()
        self.assertTrue(self.slots(day=today + timedelta(days=60)))
        self.assertEqual(self.slots(day=today + timedelta(days=61)), [])

        self.set_policy(self.other_salon, max_booking_horizon_days=90)
        self.assertTrue(self.slots(self.other_salon, day=today + timedelta(days=75)))
        self.assertEqual(self.slots(day=today + timedelta(days=75)), [])

    def test_public_booking_rejects_dates_beyond_horizon(self):
        self.set_policy(max_booking_horizon_days=10)
        far_day = timezone.localdate() + timedelta(days=11)
        self.verify_guest()

        response = self.client.get(
            reverse("booking-slots", args=[self.salon.slug]),
            {"branch": self.branch.id, "service": self.service.id, "professional": self.professional.id, "date": far_day.isoformat()},
        )
        self.assertNotContains(response, 'name="slot"')

        response = self.post_booking(local(far_day, 10), day=far_day)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "hasta 10 días de anticipación")
        self.assertFalse(Reservation.objects.filter(email=EMAIL).exists())

    def test_public_booking_rejects_slot_inside_min_notice(self):
        self.set_policy(min_booking_notice_minutes=4320)  # 3 days, beyond self.day
        self.verify_guest()
        response = self.post_booking(local(self.day, 10))
        self.assertContains(response, "Ese horario ya no está disponible")
        self.assertFalse(Reservation.objects.filter(email=EMAIL).exists())

    # Límite diario

    def test_daily_limit_is_configurable(self):
        self.set_policy(max_daily_bookings_per_client=2)
        self.create_reservation(local(self.day, 9))
        self.create_reservation(local(self.day, 9, 30))
        self.verify_guest()
        response = self.post_booking(local(self.day, 11))
        self.assertContains(response, "Ya tenés 2 reservas activas para esa fecha")
        self.assertEqual(Reservation.objects.filter(salon=self.salon, email=EMAIL).count(), 2)

        self.set_policy(max_daily_bookings_per_client=3)
        response = self.post_booking(local(self.day, 11))
        self.assertRedirects(response, reverse("booking-success", args=[self.salon.slug]))

    def test_daily_limit_message_uses_singular(self):
        self.set_policy(max_daily_bookings_per_client=1)
        self.create_reservation(local(self.day, 9))
        self.verify_guest()
        response = self.post_booking(local(self.day, 11))
        self.assertContains(response, "Ya tenés 1 reserva activa para esa fecha")

    def test_daily_limit_counts_only_own_salon(self):
        self.set_policy(max_daily_bookings_per_client=1)
        self.create_reservation(local(self.day, 9), salon=self.other_salon)
        self.verify_guest()
        response = self.post_booking(local(self.day, 11))
        self.assertRedirects(response, reverse("booking-success", args=[self.salon.slug]))

    def test_exception_allows_one_booking_above_configured_limit(self):
        self.set_policy(max_daily_bookings_per_client=1)
        self.create_reservation(local(self.day, 9))
        exception = BookingLimitException.objects.create(
            salon=self.salon, customer_email=EMAIL, booking_date=self.day, reason="Cliente frecuente", created_by=self.owner,
        )
        self.verify_guest()
        response = self.post_booking(local(self.day, 11))
        self.assertRedirects(response, reverse("booking-success", args=[self.salon.slug]))
        exception.refresh_from_db()
        self.assertIsNotNone(exception.used_at)

    def test_exceptions_page_shows_configured_limit(self):
        self.set_policy(max_daily_bookings_per_client=7)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("booking-limit-exceptions", args=[self.salon.slug]))
        self.assertContains(response, "máximo de 7 reservas activas")
        self.assertNotContains(response, "cinco")

    # Bloqueo por cancelaciones

    def cancellations(self, *offsets_hours, salon=None, now):
        for offset in offsets_hours:
            self.create_reservation(
                now + timedelta(days=10, hours=offset), salon=salon,
                status=Reservation.Status.CANCELLED_CLIENT, cancelled_at=now - timedelta(hours=offset),
            )

    def block(self, salon=None, now=None):
        return active_cancellation_booking_block(salon=salon or self.salon, customer_email=EMAIL, now=now)

    def test_cancellation_block_threshold_is_configurable(self):
        now = timezone.now()
        self.cancellations(3, 2, now=now)
        self.assertIsNone(self.block(now=now))
        self.set_policy(cancellation_block_threshold=2)
        self.assertIsNotNone(self.block(now=now))

    def test_cancellation_block_window_days_is_configurable(self):
        now = timezone.now()
        self.cancellations(1, 24 * 8, 24 * 9, now=now)
        self.assertIsNotNone(self.block(now=now))
        self.set_policy(cancellation_block_window_days=7)
        self.assertIsNone(self.block(now=now))

    def test_cancellation_block_hours_is_configurable(self):
        now = timezone.now()
        self.cancellations(5, 4, 3, now=now)
        block = self.block(now=now)
        self.assertEqual(block.unlocks_at, now - timedelta(hours=3) + timedelta(hours=24))
        self.set_policy(cancellation_block_hours=2)
        self.assertIsNone(self.block(now=now))
        self.set_policy(cancellation_block_hours=4)
        self.assertEqual(self.block(now=now).unlocks_at, now - timedelta(hours=3) + timedelta(hours=4))

    def test_cancellation_block_uses_policy_of_its_own_salon(self):
        now = timezone.now()
        self.set_policy(self.other_salon, cancellation_block_threshold=1)
        self.cancellations(2, now=now)
        self.assertIsNone(self.block(now=now))
        self.assertIsNone(self.block(self.other_salon, now=now))
        self.cancellations(2, salon=self.other_salon, now=now)
        self.assertIsNotNone(self.block(self.other_salon, now=now))
        self.assertIsNone(self.block(now=now))

    def test_booking_view_applies_configured_block(self):
        self.set_policy(cancellation_block_threshold=1, cancellation_block_hours=6)
        now = timezone.now()
        self.cancellations(1, now=now)
        self.verify_guest()
        response = self.post_booking(local(self.day, 11))
        self.assertContains(response, "No podés crear una nueva reserva por el momento")
        self.assertFalse(Reservation.objects.filter(email=EMAIL, status=Reservation.Status.CONFIRMED).exists())

    # Reprogramación

    def test_rescheduling_uses_salon_slot_interval_and_horizon(self):
        reservation = self.create_reservation(local(self.day, 9))
        self.set_policy(slot_interval_minutes=30, max_booking_horizon_days=10)
        starts = [timezone.localtime(slot).time() for slot in slots_for_reservation(reservation, self.day)][:3]
        # The reservation being moved does not block its own current time.
        self.assertEqual(starts, [time(9), time(9, 30), time(10)])
        self.assertEqual(slots_for_reservation(reservation, timezone.localdate() + timedelta(days=11)), [])

    def test_staff_rescheduling_respects_configured_daily_limit(self):
        self.set_policy(max_daily_bookings_per_client=1)
        target_day = self.day + timedelta(days=1)
        reservation = self.create_reservation(local(self.day, 9))
        self.create_reservation(local(target_day, 9))
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("reservation-reschedule", args=[reservation.id]),
            {"date": target_day.isoformat(), "slot": local(target_day, 11).isoformat()},
        )
        self.assertContains(response, "El cliente ya tiene 1 reserva activa para esa fecha")
        self.assertEqual(ReservationReschedule.objects.count(), 0)

        self.set_policy(max_daily_bookings_per_client=2)
        response = self.client.post(
            reverse("reservation-reschedule", args=[reservation.id]),
            {"date": target_day.isoformat(), "slot": local(target_day, 11).isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ReservationReschedule.objects.count(), 1)

    def test_client_rescheduling_rejects_date_beyond_horizon(self):
        reservation = self.create_reservation(local(self.day, 9))
        self.set_policy(max_booking_horizon_days=10)
        far_day = timezone.localdate() + timedelta(days=11)
        response = self.client.post(
            reverse("client-reschedule", args=[self.salon.slug, reservation.cancellation_token]),
            {"date": far_day.isoformat(), "slot": local(far_day, 11).isoformat()},
        )
        self.assertContains(response, "hasta 10 días de anticipación")
        reservation.refresh_from_db()
        self.assertEqual(timezone.localtime(reservation.starts_at), local(self.day, 9))

    # Autorización

    def test_permission_defaults_by_role(self):
        memberships = {m.role: m for m in Membership.objects.filter(salon=self.salon)}
        self.assertTrue(membership_has_permission(memberships[Membership.Role.OWNER], MANAGE_OPERATIONAL_SETTINGS))
        self.assertFalse(membership_has_permission(memberships[Membership.Role.ADMIN], MANAGE_OPERATIONAL_SETTINGS))
        self.assertFalse(membership_has_permission(memberships[Membership.Role.HAIRDRESSER], MANAGE_OPERATIONAL_SETTINGS))
        self.assertFalse(membership_has_permission(None, MANAGE_OPERATIONAL_SETTINGS))
        inactive_owner = memberships[Membership.Role.OWNER]
        inactive_owner.active = False
        self.assertFalse(membership_has_permission(inactive_owner, MANAGE_OPERATIONAL_SETTINGS))

    def test_owner_can_update_all_policies(self):
        self.client.force_login(self.owner)
        payload = self.policy_payload(
            slot_interval_minutes=30, min_booking_notice_minutes=120, max_booking_horizon_days=45,
            max_daily_bookings_per_client=2, cancellation_notice_hours=12, cancellation_block_threshold=4,
            cancellation_block_window_days=14, cancellation_block_hours=48,
        )
        response = self.client.post(reverse("salon-settings", args=[self.salon.slug]), payload)
        self.assertContains(response, "Configuración guardada")
        self.salon.refresh_from_db()
        for field, value in payload.items():
            self.assertEqual(getattr(self.salon, field), value, field)
        self.other_salon.refresh_from_db()
        self.assertEqual(self.other_salon.slot_interval_minutes, 15)

    def test_owner_form_rejects_invalid_policies(self):
        self.client.force_login(self.owner)
        url = reverse("salon-settings", args=[self.salon.slug])
        for changes in (
            {"slot_interval_minutes": 7},
            {"max_daily_bookings_per_client": 0},
            {"min_booking_notice_minutes": 1440, "max_booking_horizon_days": 1},
        ):
            with self.subTest(changes=changes):
                response = self.client.post(url, self.policy_payload(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Configuración guardada")
        self.salon.refresh_from_db()
        self.assertEqual(self.salon.slot_interval_minutes, 15)
        self.assertEqual(self.salon.max_daily_bookings_per_client, 5)

    def test_admin_sees_policies_read_only_and_cannot_update(self):
        self.client.force_login(self.admin)
        url = reverse("salon-settings", args=[self.salon.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="max_daily_bookings_per_client"')
        self.assertContains(response, "Solo el owner puede modificar estas políticas")
        self.assertContains(response, reverse("availability-settings", args=[self.salon.slug]))

        response = self.client.post(url, self.policy_payload(max_daily_bookings_per_client=1))
        self.assertEqual(response.status_code, 403)
        self.salon.refresh_from_db()
        self.assertEqual(self.salon.max_daily_bookings_per_client, 5)

    def test_hairdresser_cannot_view_or_update_policies(self):
        self.client.force_login(self.hairdresser)
        url = reverse("salon-settings", args=[self.salon.slug])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, self.policy_payload(max_daily_bookings_per_client=1)).status_code, 403)
        self.salon.refresh_from_db()
        self.assertEqual(self.salon.max_daily_bookings_per_client, 5)

    def test_owner_cannot_update_another_salon(self):
        self.client.force_login(self.other_owner)
        response = self.client.post(
            reverse("salon-settings", args=[self.salon.slug]),
            self.policy_payload(max_daily_bookings_per_client=1),
        )
        self.assertEqual(response.status_code, 404)
        self.salon.refresh_from_db()
        self.assertEqual(self.salon.max_daily_bookings_per_client, 5)

    # Navegación

    def nav_settings_link(self, salon=None):
        url = reverse("salon-settings", args=[(salon or self.salon).slug])
        return f'<a class="nav-link" href="{url}">Configuración</a>'

    def test_owner_sees_settings_in_navigation_and_can_follow_it(self):
        self.client.force_login(self.owner)
        for page in (reverse("dashboard"), reverse("agenda"), reverse("statistics", args=[self.salon.slug])):
            with self.subTest(page=page):
                self.assertContains(self.client.get(page), self.nav_settings_link(), html=True)
        self.assertNotContains(self.client.get(reverse("agenda")), self.nav_settings_link(self.other_salon), html=True)

        response = self.client.get(reverse("salon-settings", args=[self.salon.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="max_daily_bookings_per_client"')

    def test_staff_without_permission_do_not_see_settings_in_navigation(self):
        for user in (self.admin, self.hairdresser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("agenda"))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, ">Configuración<")

    def test_navigation_follows_permission_instead_of_role(self):
        granted = {Membership.Role.ADMIN: frozenset({MANAGE_OPERATIONAL_SETTINGS}), Membership.Role.HAIRDRESSER: frozenset()}
        with patch.dict("salons.access.DEFAULT_ROLE_PERMISSIONS", granted):
            self.client.force_login(self.admin)
            self.assertContains(self.client.get(reverse("agenda")), self.nav_settings_link(), html=True)

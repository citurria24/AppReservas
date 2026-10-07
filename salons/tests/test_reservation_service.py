from datetime import datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from salons.models import (
    BookingLimitException,
    Branch,
    BranchService,
    HairSalon,
    Membership,
    Professional,
    ProfessionalAbsence,
    ProfessionalBranch,
    ProfessionalService,
    Reservation,
    ReservationReschedule,
    RewardProgram,
    RewardRedemption,
    ScheduleBreak,
    Service,
    WorkSchedule,
)
from salons.rescheduling import RescheduleError, reschedule_reservation
from salons.reservation_service import (
    CancellationBlockActive,
    CustomerIdentity,
    DailyLimitReached,
    SlotUnavailable,
    create_reservation,
)


LOCAL_TZ = ZoneInfo(settings.TIME_ZONE)
EMAIL = "cliente@servicio.test"


def local(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=LOCAL_TZ)


def next_monday():
    # Dos días de margen para que la anticipación y la hora actual no interfieran.
    candidate = timezone.localdate() + timedelta(days=2)
    while candidate.weekday() != 0:
        candidate += timedelta(days=1)
    return candidate


class ReservationServiceFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("svc-owner", "owner@svc.test", "test-pass-123")
        cls.other_owner = User.objects.create_user("svc-other", "other@svc.test", "test-pass-123")
        cls.salon, cls.branch, cls.service, cls.professional = cls.build_salon("Servicio", "servicio", cls.owner)
        cls.other_salon, cls.other_branch, cls.other_service, cls.other_professional = cls.build_salon(
            "Otra", "otra-servicio", cls.other_owner,
        )
        cls.offering = BranchService.objects.get(branch=cls.branch, service=cls.service)
        cls.day = next_monday()
        cls.customer = CustomerIdentity(email=EMAIL, first_name="Cliente", last_name="Demo", contact="099 000 000")

    @classmethod
    def build_salon(cls, name, slug, owner):
        salon = HairSalon.objects.create(name=name, slug=slug)
        Membership.objects.create(salon=salon, user=owner, role=Membership.Role.OWNER)
        branch = Branch.objects.create(salon=salon, name="Centro", address="Principal 1")
        service = Service.objects.create(salon=salon, name="Corte")
        professional = Professional.objects.create(salon=salon, display_name=f"Pro {name}")
        ProfessionalBranch.objects.create(professional=professional, branch=branch)
        ProfessionalService.objects.create(professional=professional, service=service)
        BranchService.objects.create(branch=branch, service=service, duration_minutes=30)
        schedule = WorkSchedule.objects.create(
            professional=professional, branch=branch, weekday=0, starts_at=time(9), ends_at=time(18),
        )
        ScheduleBreak.objects.create(schedule=schedule, starts_at=time(13), ends_at=time(14))
        return salon, branch, service, professional

    def create(self, starts_at, **overrides):
        values = {
            "salon": self.salon, "branch": self.branch, "service": self.service,
            "professional": self.professional, "starts_at": starts_at, "customer": self.customer,
        }
        values.update(overrides)
        return create_reservation(**values)

    def set_policy(self, **values):
        HairSalon.objects.filter(pk=self.salon.pk).update(**values)
        self.salon.refresh_from_db()

    def existing(self, starts_at, *, salon=None, email=EMAIL, professional=None, status=Reservation.Status.CONFIRMED, **extra):
        salon = salon or self.salon
        own = salon == self.salon
        return Reservation.objects.create(
            salon=salon,
            branch=self.branch if own else self.other_branch,
            service=self.service if own else self.other_service,
            professional=professional or (self.professional if own else self.other_professional),
            first_name="Cliente", last_name="Demo", email=email, contact="099",
            starts_at=starts_at, ends_at=starts_at + timedelta(minutes=30), duration_minutes=30,
            status=status, **extra,
        )

    def exception(self, day, *, salon=None, used_by=None):
        salon = salon or self.salon
        return BookingLimitException.objects.create(
            salon=salon, customer_email=EMAIL, booking_date=day, reason="Grupo familiar",
            created_by=self.owner if salon == self.salon else self.other_owner,
            reservation=used_by, used_at=timezone.now() if used_by else None,
        )


class CreateReservationTests(ReservationServiceFixture):
    def assert_rejected(self, starts_at, **overrides):
        with self.assertRaises(SlotUnavailable):
            self.create(starts_at, **overrides)

    def test_valid_reservation_is_persisted_with_salon_rules(self):
        self.set_policy(cancellation_notice_hours=12)
        reservation = self.create(local(self.day, 10), notes="Primera vez")
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assertEqual(reservation.salon, self.salon)
        self.assertEqual(reservation.email, EMAIL)
        self.assertEqual(reservation.first_name, "Cliente")
        self.assertEqual(reservation.ends_at, local(self.day, 10, 30))
        self.assertEqual(reservation.cancellation_notice_hours, 12)
        self.assertEqual(reservation.reward_discount_percent, 0)
        self.assertEqual(reservation.notes, "Primera vez")

    def test_duration_comes_from_current_offering_and_is_kept(self):
        BranchService.objects.filter(pk=self.offering.pk).update(duration_minutes=45)
        reservation = self.create(local(self.day, 10))
        self.assertEqual(reservation.duration_minutes, 45)
        self.assertEqual(reservation.ends_at, local(self.day, 10, 45))
        BranchService.objects.filter(pk=self.offering.pk).update(duration_minutes=20)
        reservation.refresh_from_db()
        self.assertEqual(reservation.duration_minutes, 45)
        self.assertEqual(reservation.ends_at, local(self.day, 10, 45))

    def test_objects_from_another_salon_are_rejected(self):
        for label, overrides in {
            "sucursal": {"branch": self.other_branch},
            "servicio": {"service": self.other_service},
            "profesional": {"professional": self.other_professional},
            "peluquería": {"salon": self.other_salon},
        }.items():
            with self.subTest(label):
                self.assert_rejected(local(self.day, 10), **overrides)
        self.assertFalse(Reservation.objects.exists())

    def test_inactive_professional_is_rejected(self):
        Professional.objects.filter(pk=self.professional.pk).update(active=False)
        self.professional.refresh_from_db()
        self.assert_rejected(local(self.day, 10))

    def test_invalid_service_or_branch_is_rejected(self):
        unassigned = Professional.objects.create(salon=self.salon, display_name="Sin asignar")
        not_offered = Service.objects.create(salon=self.salon, name="Barba")
        ProfessionalService.objects.create(professional=self.professional, service=not_offered)
        cases = [
            ("profesional sin sucursal", {"professional": unassigned}, None),
            ("servicio no ofrecido", {"service": not_offered}, None),
            ("oferta inactiva", {}, (BranchService, self.offering.pk)),
            ("sucursal inactiva", {}, (Branch, self.branch.pk)),
            ("servicio inactivo", {}, (Service, self.service.pk)),
            ("sin el servicio", {}, (ProfessionalService, None)),
        ]
        for label, overrides, deactivate in cases:
            with self.subTest(label):
                if deactivate and deactivate[0] is ProfessionalService:
                    ProfessionalService.objects.filter(professional=self.professional, service=self.service).delete()
                elif deactivate:
                    deactivate[0].objects.filter(pk=deactivate[1]).update(active=False)
                self.assert_rejected(
                    local(self.day, 10),
                    branch=Branch.objects.get(pk=self.branch.pk),
                    service=overrides.get("service", Service.objects.get(pk=self.service.pk)),
                    professional=overrides.get("professional", self.professional),
                )
                if deactivate and deactivate[0] is ProfessionalService:
                    ProfessionalService.objects.create(professional=self.professional, service=self.service)
                elif deactivate:
                    deactivate[0].objects.filter(pk=deactivate[1]).update(active=True)
        self.assertFalse(Reservation.objects.exists())

    def test_absence_blocks_slot(self):
        ProfessionalAbsence.objects.create(
            professional=self.professional, branch=self.branch,
            starts_at=local(self.day, 10), ends_at=local(self.day, 11),
        )
        self.assert_rejected(local(self.day, 10))
        self.assert_rejected(local(self.day, 9, 45))
        self.assertTrue(self.create(local(self.day, 11)))

    def test_break_closing_and_schedule_grid_are_respected(self):
        self.assert_rejected(local(self.day, 13))
        self.assert_rejected(local(self.day, 12, 45))
        self.assert_rejected(local(self.day, 17, 45))
        self.assert_rejected(local(self.day, 8, 30))
        self.assert_rejected(local(self.day, 10, 5))
        self.assert_rejected(local(self.day + timedelta(days=1), 10))  # martes sin jornada

    def test_overlap_with_confirmed_reservation_is_rejected(self):
        self.existing(local(self.day, 10), email="otra@servicio.test")
        self.assert_rejected(local(self.day, 10))
        self.assert_rejected(local(self.day, 9, 45))
        self.assertTrue(self.create(local(self.day, 10, 30)))

    def test_minimum_notice_is_applied(self):
        self.set_policy(min_booking_notice_minutes=120)
        with patch("django.utils.timezone.now", return_value=local(self.day, 9)):
            self.assert_rejected(local(self.day, 10, 45))
            self.assertTrue(self.create(local(self.day, 11)))

    def test_maximum_horizon_is_applied(self):
        self.set_policy(max_booking_horizon_days=1)
        self.assert_rejected(local(self.day, 10))

    def test_daily_limit_uses_salon_policy_and_case_insensitive_identity(self):
        self.set_policy(max_daily_bookings_per_client=1)
        self.existing(local(self.day, 9), email=EMAIL.upper())
        with self.assertRaises(DailyLimitReached) as raised:
            self.create(local(self.day, 11))
        self.assertEqual(raised.exception.limit, 1)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_daily_limit_ignores_other_days_salons_and_inactive_reservations(self):
        self.set_policy(max_daily_bookings_per_client=1)
        self.existing(local(self.day + timedelta(days=7), 9))
        self.existing(local(self.day, 9), salon=self.other_salon)
        self.existing(local(self.day, 9, 30), status=Reservation.Status.CANCELLED_CLIENT, cancelled_at=timezone.now())
        self.assertTrue(self.create(local(self.day, 11)))

    def test_valid_exception_allows_one_booking_and_is_consumed(self):
        self.set_policy(max_daily_bookings_per_client=1)
        self.existing(local(self.day, 9))
        exception = self.exception(self.day)
        reservation = self.create(local(self.day, 11))
        exception.refresh_from_db()
        self.assertEqual(exception.reservation, reservation)
        self.assertIsNotNone(exception.used_at)
        with self.assertRaises(DailyLimitReached):
            self.create(local(self.day, 15))

    def test_used_exception_does_not_authorize(self):
        self.set_policy(max_daily_bookings_per_client=1)
        first = self.existing(local(self.day, 9))
        self.exception(self.day, used_by=first)
        with self.assertRaises(DailyLimitReached):
            self.create(local(self.day, 11))

    def test_exception_of_another_salon_or_day_does_not_authorize(self):
        self.set_policy(max_daily_bookings_per_client=1)
        self.existing(local(self.day, 9))
        other_salon_exception = self.exception(self.day, salon=self.other_salon)
        other_day_exception = self.exception(self.day + timedelta(days=7))
        with self.assertRaises(DailyLimitReached):
            self.create(local(self.day, 11))
        for exception in (other_salon_exception, other_day_exception):
            exception.refresh_from_db()
            self.assertIsNone(exception.used_at)

    def test_cancellation_block_is_applied(self):
        self.set_policy(cancellation_block_threshold=1)
        self.existing(
            local(self.day + timedelta(days=14), 9), status=Reservation.Status.CANCELLED_CLIENT,
            cancelled_at=timezone.now() - timedelta(hours=1),
        )
        with self.assertRaises(CancellationBlockActive) as raised:
            self.create(local(self.day, 10))
        self.assertIsNotNone(raised.exception.block.unlocks_at)
        self.assertEqual(Reservation.objects.filter(status=Reservation.Status.CONFIRMED).count(), 0)

    def test_reward_is_applied_once_per_period(self):
        RewardProgram.objects.create(salon=self.salon, active=True, services_required=1, discount_percent=15)
        self.existing(
            datetime.combine(timezone.localdate(), time(0), tzinfo=LOCAL_TZ), status=Reservation.Status.COMPLETED,
        )
        rewarded = self.create(local(self.day, 10))
        self.assertEqual(rewarded.reward_discount_percent, 15)
        redemption = RewardRedemption.objects.get()
        self.assertEqual(redemption.reservation, rewarded)
        self.assertEqual(redemption.attended_services, 1)
        self.assertEqual(self.create(local(self.day, 11)).reward_discount_percent, 0)
        self.assertEqual(RewardRedemption.objects.count(), 1)

    def test_race_on_database_constraint_is_reported_without_side_effects(self):
        # Simula que otra transacción ocupó el horario después del cálculo de disponibilidad.
        self.set_policy(max_daily_bookings_per_client=1)
        self.existing(local(self.day, 9, 30), email="otra@servicio.test")
        self.existing(local(self.day, 15))
        exception = self.exception(self.day)
        with patch("salons.reservation_service.available_slots", return_value=[local(self.day, 9, 30)]):
            with self.assertRaisesMessage(SlotUnavailable, "acaba de ocuparse"):
                self.create(local(self.day, 9, 30))
        exception.refresh_from_db()
        self.assertIsNone(exception.used_at)
        self.assertEqual(Reservation.objects.count(), 2)

    def test_notify_runs_after_persistence_and_its_failure_rolls_back(self):
        self.set_policy(max_daily_bookings_per_client=1)
        self.existing(local(self.day, 15))
        exception = self.exception(self.day)
        RewardProgram.objects.create(salon=self.salon, active=True, services_required=1, discount_percent=10)
        self.existing(datetime.combine(timezone.localdate(), time(0), tzinfo=LOCAL_TZ), status=Reservation.Status.COMPLETED)
        before = Reservation.objects.count()

        def failing_notify(reservation):
            self.assertTrue(Reservation.objects.filter(pk=reservation.pk).exists())
            raise RuntimeError("smtp caído")

        with self.assertRaises(RuntimeError):
            self.create(local(self.day, 10), notify=failing_notify)
        self.assertEqual(Reservation.objects.count(), before)
        self.assertFalse(RewardRedemption.objects.exists())
        exception.refresh_from_db()
        self.assertIsNone(exception.used_at)

        notified = []
        reservation = self.create(local(self.day, 10), notify=notified.append)
        self.assertEqual(notified, [reservation])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RescheduleDailyLimitTests(ReservationServiceFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        HairSalon.objects.filter(pk=cls.salon.pk).update(max_daily_bookings_per_client=1)
        cls.salon.refresh_from_db()
        cls.target_day = cls.day + timedelta(days=7)

    def reschedule(self, reservation, day, hour):
        return reschedule_reservation(
            reservation=reservation, day=day, slot_value=local(day, hour).isoformat(),
            source=ReservationReschedule.Source.SALON, changed_by=self.owner, request=RequestFactory().get("/"),
        )

    def assert_not_moved(self, reservation, starts_at):
        reservation.refresh_from_db()
        self.assertEqual(reservation.starts_at, starts_at)
        self.assertFalse(ReservationReschedule.objects.filter(reservation=reservation).exists())

    def test_same_day_move_at_limit_is_allowed_and_consumes_nothing(self):
        first = self.existing(local(self.day, 10))
        extra = self.existing(local(self.day, 15))
        self.exception(self.day, used_by=extra)
        spare = self.exception(self.day)
        self.reschedule(extra, self.day, 16)
        self.reschedule(first, self.day, 11)
        extra.refresh_from_db()
        self.assertEqual(extra.starts_at, local(self.day, 16))
        spare.refresh_from_db()
        self.assertIsNone(spare.used_at)
        self.assertEqual(BookingLimitException.objects.filter(used_at__isnull=False).count(), 1)

    def test_other_day_below_limit_is_allowed(self):
        reservation = self.existing(local(self.day, 10))
        self.reschedule(reservation, self.target_day, 10)
        reservation.refresh_from_db()
        self.assertEqual(reservation.starts_at, local(self.target_day, 10))
        self.assertFalse(BookingLimitException.objects.exists())

    def test_other_day_at_limit_without_exception_is_rejected(self):
        reservation = self.existing(local(self.day, 10))
        self.existing(local(self.target_day, 9))
        with self.assertRaisesMessage(RescheduleError, "1 reserva activa"):
            self.reschedule(reservation, self.target_day, 11)
        self.assert_not_moved(reservation, local(self.day, 10))

    def test_other_day_with_exception_is_allowed_and_consumes_it_once(self):
        reservation = self.existing(local(self.day, 10))
        origin_exception = self.exception(self.day, used_by=reservation)
        self.existing(local(self.target_day, 9))
        target_exception = self.exception(self.target_day)
        self.reschedule(reservation, self.target_day, 11)
        target_exception.refresh_from_db()
        origin_exception.refresh_from_db()
        self.assertEqual(target_exception.reservation, reservation)
        self.assertIsNotNone(target_exception.used_at)
        # La excepción del día de origen sigue registrada como usada por la misma reserva.
        self.assertEqual(origin_exception.reservation, reservation)
        self.assertEqual(reservation.limit_exceptions.count(), 2)
        other = self.existing(local(self.day, 12))
        with self.assertRaises(RescheduleError):
            self.reschedule(other, self.target_day, 15)

    def test_origin_day_exception_does_not_authorize_destination(self):
        reservation = self.existing(local(self.day, 10))
        unused_origin = self.exception(self.day)
        used_origin = self.exception(self.day, used_by=self.existing(local(self.day, 15)))
        self.existing(local(self.target_day, 9))
        with self.assertRaises(RescheduleError):
            self.reschedule(reservation, self.target_day, 11)
        self.assert_not_moved(reservation, local(self.day, 10))
        unused_origin.refresh_from_db()
        self.assertIsNone(unused_origin.used_at)
        used_origin.refresh_from_db()
        self.assertNotEqual(used_origin.reservation, reservation)

    def test_exception_of_another_salon_authorizes_nothing(self):
        reservation = self.existing(local(self.day, 10))
        self.existing(local(self.target_day, 9))
        foreign = self.exception(self.target_day, salon=self.other_salon)
        with self.assertRaises(RescheduleError):
            self.reschedule(reservation, self.target_day, 11)
        self.assert_not_moved(reservation, local(self.day, 10))
        foreign.refresh_from_db()
        self.assertIsNone(foreign.used_at)

    def test_reservations_of_another_salon_do_not_count_for_destination(self):
        reservation = self.existing(local(self.day, 10))
        self.existing(local(self.target_day, 9), salon=self.other_salon)
        self.reschedule(reservation, self.target_day, 11)
        reservation.refresh_from_db()
        self.assertEqual(reservation.starts_at, local(self.target_day, 11))

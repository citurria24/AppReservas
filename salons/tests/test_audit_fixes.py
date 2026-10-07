"""Regresiones de los bugs confirmados en la auditoría (bloque B2)."""
import json
from datetime import datetime, time, timedelta
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from salons.booking import available_slots
from salons.models import (
    BookingLimitException,
    Branch,
    BranchService,
    HairSalon,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    Reservation,
    ReservationReschedule,
    ReservationStatusChange,
    RewardRedemption,
    ScheduleBreak,
    Service,
    WorkSchedule,
)
from salons.rescheduling import RescheduleError, reschedule_reservation, slots_for_reservation
from salons.reservation_status import change_reservation_status, reservation_actions
from salons.tests import test_agenda, test_rescheduling


LOCAL_TZ = ZoneInfo(settings.TIME_ZONE)


def local(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=LOCAL_TZ)


class AgendaBranchFilterTests(TestCase):
    """Bug 1: /agenda/?branch=... no debe responder 500 ni filtrar datos ajenos."""

    @classmethod
    def setUpTestData(cls):
        test_agenda.AgendaPermissionTests.setUpTestData.__func__(cls)

    create_reservation = classmethod(test_agenda.AgendaPermissionTests.create_reservation.__func__)

    def get_agenda(self, user, branch, **extra):
        self.client.force_login(user)
        return self.client.get(reverse("agenda"), {"date": self.day.isoformat(), "branch": branch}, **extra)

    def test_non_numeric_branch_is_a_bad_request(self):
        for value in ("abc", "1abc", " ", "²", "1.5"):
            for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
                with self.subTest(value=value, headers=headers):
                    self.assertEqual(self.get_agenda(self.owner, value, **headers).status_code, 400)

    def test_unknown_or_foreign_branch_is_not_found_without_leaking_data(self):
        missing = Branch.objects.order_by("-pk").first().pk + 1000
        for value in (missing, -1, 10**30, self.foreign_branch.pk):
            with self.subTest(value=value):
                response = self.get_agenda(self.owner, value)
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, "Cliente ajeno", status_code=404)
                self.assertNotContains(response, self.foreign_branch.name, status_code=404)

    def test_unknown_and_foreign_branch_are_indistinguishable(self):
        missing = Branch.objects.order_by("-pk").first().pk + 1000
        foreign = self.get_agenda(self.owner, self.foreign_branch.pk)
        unknown = self.get_agenda(self.owner, missing)
        self.assertEqual(foreign.status_code, unknown.status_code)
        self.assertEqual(foreign.content, unknown.content)

    def test_branch_of_same_salon_without_authorization_is_not_found(self):
        for user in (self.admin, self.hairdresser):
            with self.subTest(user=user.username):
                self.assertEqual(self.get_agenda(user, self.other_branch_same_salon.pk).status_code, 404)

    def test_authorized_branch_still_filters(self):
        other_branch_reservation = self.create_reservation(
            self.salon, self.other_branch_same_salon, self.service, self.colleague,
            self.own_reservation.starts_at + timedelta(hours=2), "Cliente este",
        )
        response = self.get_agenda(self.owner, self.branch.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente propio")
        self.assertNotContains(response, other_branch_reservation.first_name)
        self.assertEqual(self.get_agenda(self.admin, self.branch.pk).status_code, 200)

    def test_empty_branch_keeps_showing_every_accessible_branch(self):
        response = self.get_agenda(self.owner, "")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente propio")
        self.assertNotContains(response, "Cliente ajeno")


class OperationalStatusTimingTests(TestCase):
    """Bug 2: Atendida/Ausente solo desde Reservation.starts_at."""

    @classmethod
    def setUpTestData(cls):
        test_agenda.AgendaPermissionTests.setUpTestData.__func__(cls)

    create_reservation = classmethod(test_agenda.AgendaPermissionTests.create_reservation.__func__)

    def at(self, moment):
        return patch("django.utils.timezone.now", return_value=moment)

    def post_view(self, user, action):
        self.client.force_login(user)
        return self.client.post(reverse("reservation-status", args=[self.own_reservation.pk]), {"action": action})

    def post_api(self, user, action):
        self.client.force_login(user)
        return self.client.post(
            reverse("api-reservation-action", args=[self.own_reservation.pk]),
            data=json.dumps({"action": action}),
            content_type="application/json",
        )

    def assert_unchanged(self):
        self.own_reservation.refresh_from_db()
        self.assertEqual(self.own_reservation.status, Reservation.Status.CONFIRMED)
        self.assertFalse(ReservationStatusChange.objects.exists())

    def test_service_rejects_attended_and_absent_before_start(self):
        before_start = self.own_reservation.starts_at - timedelta(seconds=1)
        for action in ("complete", "no_show"):
            with self.subTest(action=action), self.at(before_start):
                with self.assertRaises(PermissionDenied):
                    change_reservation_status(user=self.owner, pk=self.own_reservation.pk, action=action)
        self.assert_unchanged()

    def test_django_view_rejects_future_attended_and_absent_for_every_role(self):
        for user in (self.owner, self.admin, self.hairdresser):
            for action in ("complete", "no_show"):
                with self.subTest(user=user.username, action=action):
                    self.assertEqual(self.post_view(user, action).status_code, 403)
        self.assert_unchanged()

    def test_api_rejects_future_attended_and_absent(self):
        for action in ("mark_attended", "mark_absent"):
            with self.subTest(action=action):
                self.assertEqual(self.post_api(self.owner, action).status_code, 403)
        self.assert_unchanged()

    def test_allowed_exactly_from_start(self):
        S = Reservation.Status
        for action, target in (("complete", S.COMPLETED), ("no_show", S.NO_SHOW)):
            with self.subTest(action=action):
                Reservation.objects.filter(pk=self.own_reservation.pk).update(status=S.CONFIRMED)
                with self.at(self.own_reservation.starts_at):
                    self.assertEqual(self.post_view(self.hairdresser, action).status_code, 302)
                self.own_reservation.refresh_from_db()
                self.assertEqual(self.own_reservation.status, target)

    def test_api_allows_after_start(self):
        with self.at(self.own_reservation.starts_at + timedelta(minutes=5)):
            self.assertEqual(self.post_api(self.admin, "mark_absent").status_code, 200)
        self.own_reservation.refresh_from_db()
        self.assertEqual(self.own_reservation.status, Reservation.Status.NO_SHOW)

    def test_local_cancellation_is_still_allowed_before_start(self):
        self.assertEqual(self.post_view(self.owner, "cancel").status_code, 302)
        self.own_reservation.refresh_from_db()
        self.assertEqual(self.own_reservation.status, Reservation.Status.CANCELLED_SALON)

    def test_available_actions_follow_the_same_rule(self):
        actions = reservation_actions(self.owner, self.own_reservation)
        self.assertFalse(actions["can_complete"])
        self.assertFalse(actions["can_no_show"])
        self.assertTrue(actions["can_cancel"])
        self.assertTrue(actions["can_reschedule"])
        with self.at(self.own_reservation.starts_at):
            actions = reservation_actions(self.owner, self.own_reservation)
        self.assertTrue(actions["can_complete"])
        self.assertTrue(actions["can_no_show"])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RescheduleHistoricalDurationTests(TestCase):
    """Bug 3: la reprogramación usa Reservation.duration_minutes, no la duración actual."""

    @classmethod
    def setUpTestData(cls):
        test_rescheduling.ReservationReschedulingTests.setUpTestData.__func__(cls)
        cls.offering = BranchService.objects.get(branch=cls.branch, service=cls.service)
        schedule = WorkSchedule.objects.get(professional=cls.professional, branch=cls.branch, weekday=0)
        ScheduleBreak.objects.create(schedule=schedule, starts_at=time(13), ends_at=time(14))
        # Reserva tomada cuando el servicio duraba 60 minutos.
        starts = local(cls.day, 10)
        Reservation.objects.filter(pk=cls.reservation.pk).update(
            duration_minutes=60, ends_at=starts + timedelta(minutes=60),
        )
        cls.reservation.refresh_from_db()
        blocker_start = local(cls.day, 12)
        Reservation.objects.create(
            salon=cls.salon, branch=cls.branch, service=cls.service, professional=cls.professional,
            first_name="Otra", last_name="Clienta", email="otra@move.test", contact="099",
            starts_at=blocker_start, ends_at=blocker_start + timedelta(minutes=30), duration_minutes=30,
        )
        # Después la sucursal acorta el servicio.
        cls.offering.duration_minutes = 30
        cls.offering.save()

    def test_existing_reservation_keeps_its_duration(self):
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.duration_minutes, 60)
        self.assertEqual(self.reservation.ends_at - self.reservation.starts_at, timedelta(minutes=60))

    def test_slots_respect_historical_duration_for_overlap_break_and_closing(self):
        slots = slots_for_reservation(self.reservation, self.day)
        self.assertIn(local(self.day, 9), slots)
        self.assertIn(local(self.day, 11), slots)
        self.assertNotIn(local(self.day, 11, 30), slots)  # 60 min pisa la reserva de las 12:00
        self.assertNotIn(local(self.day, 12, 30), slots)  # 60 min cruza el descanso de 13:00
        self.assertIn(local(self.day, 14), slots)
        self.assertIn(local(self.day, 17), slots)
        self.assertNotIn(local(self.day, 17, 30), slots)  # 60 min supera el cierre de 18:00
        # Con la duración nueva (30 min) esos horarios sí estarían libres.
        new_bookings = available_slots(
            salon=self.salon, branch=self.branch, service=self.service, professional=self.professional, day=self.day,
        )
        self.assertIn(local(self.day, 11, 30), new_bookings)
        self.assertIn(local(self.day, 17, 30), new_bookings)

    def reschedule(self, slot):
        return reschedule_reservation(
            reservation=self.reservation, day=self.day, slot_value=slot.isoformat(),
            source=ReservationReschedule.Source.SALON, changed_by=self.owner, request=RequestFactory().get("/"),
        )

    def test_reschedule_rejects_slots_that_only_fit_the_new_duration(self):
        for slot in (local(self.day, 11, 30), local(self.day, 12, 30), local(self.day, 17, 30)):
            with self.subTest(slot=slot), self.assertRaises(RescheduleError):
                self.reschedule(slot)
        self.assertFalse(ReservationReschedule.objects.exists())

    def test_reschedule_keeps_historical_duration(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("reservation-reschedule", args=[self.reservation.pk]),
            {"date": self.day.isoformat(), "slot": local(self.day, 17).isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.starts_at, local(self.day, 17))
        self.assertEqual(self.reservation.ends_at, local(self.day, 18))
        self.assertEqual(self.reservation.duration_minutes, 60)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AvailabilityGuardTests(TestCase):
    """Bug 4: sin horarios para profesionales inactivos ni combinaciones inválidas."""

    @classmethod
    def setUpTestData(cls):
        test_rescheduling.ReservationReschedulingTests.setUpTestData.__func__(cls)

    def slots(self, **overrides):
        values = {
            "salon": self.salon, "branch": self.branch, "service": self.service,
            "professional": self.professional, "day": self.day,
        }
        values.update(overrides)
        return available_slots(**values)

    def deactivate(self, obj):
        type(obj).objects.filter(pk=obj.pk).update(active=False)
        obj.refresh_from_db()

    def test_valid_combination_has_slots(self):
        self.assertTrue(self.slots())

    def test_inactive_professional_has_no_slots(self):
        self.deactivate(self.professional)
        self.assertEqual(self.slots(), [])
        self.assertEqual(slots_for_reservation(Reservation.objects.get(pk=self.reservation.pk), self.day), [])

    def test_invalid_combinations_have_no_slots(self):
        other_branch_professional = Professional.objects.create(salon=self.salon, display_name="Sin sucursal")
        ProfessionalService.objects.create(professional=other_branch_professional, service=self.service)
        ProfessionalBranch.objects.create(professional=other_branch_professional, branch=self.forbidden_branch)
        WorkSchedule.objects.create(
            professional=other_branch_professional, branch=self.forbidden_branch, weekday=0,
            starts_at=time(9), ends_at=time(18),
        )
        not_offered = Service.objects.create(salon=self.salon, name="Barba")
        ProfessionalService.objects.create(professional=self.professional, service=not_offered)
        not_trained = Service.objects.create(salon=self.salon, name="Color")
        BranchService.objects.create(branch=self.branch, service=not_trained, duration_minutes=30)
        cases = {
            "profesional de otra peluquería": {"professional": self.other_professional},
            "sucursal de otra peluquería": {"branch": self.other_branch},
            "servicio de otra peluquería": {"service": self.other_service},
            "profesional no asignado a la sucursal": {"professional": other_branch_professional},
            "servicio no ofrecido en la sucursal": {"service": not_offered},
            "profesional sin el servicio": {"service": not_trained},
        }
        for label, overrides in cases.items():
            with self.subTest(label):
                self.assertEqual(self.slots(**overrides), [])

    def test_inactive_related_objects_have_no_slots(self):
        for obj in (self.branch, self.service, BranchService.objects.get(branch=self.branch, service=self.service)):
            with self.subTest(model=type(obj).__name__):
                self.deactivate(obj)
                self.assertEqual(self.slots(branch=Branch.objects.get(pk=self.branch.pk),
                                            service=Service.objects.get(pk=self.service.pk)), [])
                type(obj).objects.filter(pk=obj.pk).update(active=True)
        self.assertTrue(self.slots())

    def test_reservation_with_inactive_professional_cannot_be_rescheduled(self):
        slot = next(s for s in slots_for_reservation(self.reservation, self.day) if s != self.reservation.starts_at)
        self.deactivate(self.professional)
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("reservation-reschedule", args=[self.reservation.pk]),
            {"date": self.day.isoformat(), "slot": slot.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ese horario ya no está disponible")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.starts_at, local(self.day, 10))
        self.assertFalse(ReservationReschedule.objects.exists())

    def test_reservation_with_inactive_professional_cannot_be_booked(self):
        slot = self.slots()[0]
        self.deactivate(self.professional)
        session = self.client.session
        session["verified_guest"] = {
            "salon_id": self.salon.id, "email": "nuevo@move.test", "first_name": "Nuevo",
            "last_name": "Cliente", "contact": "099", "verified_at": timezone.now().isoformat(),
        }
        session.save()
        response = self.client.post(reverse("booking-create", args=[self.salon.slug]), {
            "branch": self.branch.pk, "service": self.service.pk, "professional": self.professional.pk,
            "date": self.day.isoformat(), "slot": slot.isoformat(), "notes": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Reservation.objects.filter(email="nuevo@move.test").exists())
        slots_response = self.client.get(reverse("booking-slots", args=[self.salon.slug]), {
            "branch": self.branch.pk, "service": self.service.pk, "professional": self.professional.pk,
            "date": self.day.isoformat(),
        })
        self.assertNotContains(slots_response, slot.isoformat())


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RescheduleBookingLimitExceptionTests(TestCase):
    """Investigación: la reprogramación no consulta BookingLimitException.

    Estos tests documentan el comportamiento ACTUAL, que se revisará en B3
    junto con la centralización de las reglas de reserva.
    """

    @classmethod
    def setUpTestData(cls):
        test_rescheduling.ReservationReschedulingTests.setUpTestData.__func__(cls)
        HairSalon.objects.filter(pk=cls.salon.pk).update(max_daily_bookings_per_client=1)
        cls.salon.refresh_from_db()
        cls.reservation.refresh_from_db()

    def reserve(self, day, hour):
        starts = local(day, hour)
        return Reservation.objects.create(
            salon=self.salon, branch=self.branch, service=self.service, professional=self.professional,
            first_name="Cliente", last_name="Demo", email=self.reservation.email, contact="099",
            starts_at=starts, ends_at=starts + timedelta(minutes=30), duration_minutes=30,
        )

    def exception_for(self, day, reservation=None):
        return BookingLimitException.objects.create(
            salon=self.salon, customer_email=self.reservation.email, booking_date=day,
            reason="Grupo familiar", created_by=self.owner, reservation=reservation,
            used_at=timezone.now() if reservation else None,
        )

    def reschedule(self, reservation, day, hour):
        return reschedule_reservation(
            reservation=reservation, day=day, slot_value=local(day, hour).isoformat(),
            source=ReservationReschedule.Source.SALON, changed_by=self.owner, request=RequestFactory().get("/"),
        )

    def test_reservation_created_with_exception_cannot_move_within_its_own_day(self):
        extra = self.reserve(self.day, 15)
        self.exception_for(self.day, reservation=extra)
        with self.assertRaisesMessage(RescheduleError, "1 reserva activa"):
            self.reschedule(extra, self.day, 16)

    def test_unused_exception_is_neither_honored_nor_consumed_when_moving(self):
        other_day = self.day + timedelta(days=7)
        moving = self.reserve(other_day, 10)
        exception = self.exception_for(self.day)
        with self.assertRaisesMessage(RescheduleError, "1 reserva activa"):
            self.reschedule(moving, self.day, 15)
        exception.refresh_from_db()
        self.assertIsNone(exception.used_at)
        self.assertIsNone(exception.reservation_id)


class SeedDemoTests(TestCase):
    """Bug 5: seed_demo debe ser idempotente y no romper con auditoría protegida."""

    def seed(self):
        call_command("seed_demo", stdout=StringIO())

    def demo_state(self):
        return {
            "reservations": Reservation.objects.count(),
            "upcoming_demo": Reservation.objects.filter(
                email__in=["cliente.norte@example.test", "cliente.sur@example.test"],
                status=Reservation.Status.CONFIRMED,
                starts_at__gte=timezone.now(),
            ).count(),
            "professionals": Professional.objects.count(),
            "services": Service.objects.count(),
            "branch_services": BranchService.objects.count(),
            "schedules": WorkSchedule.objects.count(),
        }

    def test_runs_on_empty_database_and_repeatedly(self):
        self.seed()
        first = self.demo_state()
        self.assertEqual(first["upcoming_demo"], 2)
        self.seed()
        self.seed()
        self.assertEqual(self.demo_state(), first)

    def test_runs_after_operating_the_demo_without_deleting_audit(self):
        self.seed()
        from accounts.models import User
        owner = User.objects.get(username="owner_norte")
        norte = HairSalon.objects.get(slug="estilo-norte")
        agenda_demo = Reservation.objects.get(salon=norte, email="cliente.norte@example.test")
        with patch("django.utils.timezone.now", return_value=agenda_demo.starts_at + timedelta(minutes=1)):
            change_reservation_status(user=owner, pk=agenda_demo.pk, action="complete")

        reward_reservation = Reservation.objects.filter(
            salon=norte, email="cliente.recompensa@example.test",
        ).first()
        redeemed_start = agenda_demo.starts_at + timedelta(hours=2)
        redeemed = Reservation.objects.create(
            salon=norte, branch=reward_reservation.branch, service=reward_reservation.service,
            professional=reward_reservation.professional, first_name="Cliente", last_name="Recompensa",
            email="cliente.recompensa@example.test", contact="099",
            starts_at=redeemed_start, ends_at=redeemed_start + timedelta(minutes=30), duration_minutes=30,
        )
        RewardRedemption.objects.create(
            salon=norte, customer_email=redeemed.email, period_start=timezone.localdate().replace(day=1),
            period_end=timezone.localdate().replace(day=28), attended_services=2, discount_percent=15,
            reservation=redeemed,
        )
        change_reservation_status(user=owner, pk=redeemed.pk, action="cancel")
        audit_count = ReservationStatusChange.objects.count()

        self.seed()
        self.seed()

        self.assertEqual(ReservationStatusChange.objects.count(), audit_count)
        agenda_demo.refresh_from_db()
        self.assertEqual(agenda_demo.status, Reservation.Status.COMPLETED)
        self.assertTrue(RewardRedemption.objects.filter(reservation=redeemed).exists())
        self.assertEqual(self.demo_state()["upcoming_demo"], 2)

    def test_restores_deactivated_demo_catalog(self):
        self.seed()
        Professional.objects.update(active=False)
        Service.objects.update(active=False)
        Branch.objects.update(active=False)
        self.seed()
        self.assertFalse(Professional.objects.filter(active=False).exists())
        self.assertFalse(Service.objects.filter(active=False).exists())
        self.assertFalse(Branch.objects.filter(active=False).exists())
        self.assertEqual(self.demo_state()["upcoming_demo"], 2)

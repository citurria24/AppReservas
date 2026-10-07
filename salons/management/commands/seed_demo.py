from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from accounts.models import User
from django.conf import settings
from django.utils import timezone
from salons.booking import available_slots
from salons.rewards import available_reward
from salons.models import Branch, BranchService, HairSalon, Membership, MembershipBranch, Professional, ProfessionalBranch, ProfessionalService, Reservation, RewardProgram, ScheduleBreak, Service, WorkSchedule


class Command(BaseCommand):
    help = "Crea o actualiza los datos demostrativos de dos peluquerías aisladas."

    PASSWORD = "DemoTuTurno2026!"

    def user(self, username, first_name, email):
        user, _ = User.objects.update_or_create(username=username, defaults={"first_name": first_name, "email": email, "is_active": True})
        user.set_password(self.PASSWORD)
        user.save(update_fields=["password"])
        return user

    @transaction.atomic
    def handle(self, *args, **options):
        owner_norte = self.user("owner_norte", "Ana", "owner.norte@example.test")
        admin_norte = self.user("admin_norte", "Martín", "admin.norte@example.test")
        peluquero_norte = self.user("peluquero_norte", "Sofía", "sofia.norte@example.test")
        owner_sur = self.user("owner_sur", "Lucía", "owner.sur@example.test")

        norte, _ = HairSalon.objects.update_or_create(slug="estilo-norte", defaults={"name": "Estilo Norte", "active": True})
        sur, _ = HairSalon.objects.update_or_create(slug="casa-sur", defaults={"name": "Casa Sur", "active": True})
        centro, _ = Branch.objects.update_or_create(salon=norte, name="Centro", defaults={"address": "18 de Julio 1234", "phone": "2900 1111", "active": True})
        pocitos, _ = Branch.objects.update_or_create(salon=norte, name="Pocitos", defaults={"address": "Benito Blanco 920", "phone": "2700 2222", "active": True})
        cordon, _ = Branch.objects.update_or_create(salon=sur, name="Cordón", defaults={"address": "Gaboto 1540", "phone": "2410 3333", "active": True})

        memberships = [
            (owner_norte, norte, Membership.Role.OWNER, [centro, pocitos]),
            (admin_norte, norte, Membership.Role.ADMIN, [centro]),
            (peluquero_norte, norte, Membership.Role.HAIRDRESSER, [pocitos]),
            (owner_sur, sur, Membership.Role.OWNER, [cordon]),
        ]
        for user, salon, role, branches in memberships:
            membership, _ = Membership.objects.update_or_create(user=user, salon=salon, defaults={"role": role, "active": True})
            MembershipBranch.objects.filter(membership=membership).delete()
            for branch in branches:
                MembershipBranch.objects.create(membership=membership, branch=branch)

        sofia, _ = Professional.objects.update_or_create(salon=norte, display_name="Sofía", defaults={"user": peluquero_norte, "active": True})
        diego, _ = Professional.objects.update_or_create(salon=norte, display_name="Diego", defaults={"user": None, "active": True})
        vale, _ = Professional.objects.update_or_create(salon=sur, display_name="Valentina", defaults={"user": None, "active": True})
        for professional, branches in [(sofia, [pocitos]), (diego, [centro]), (vale, [cordon])]:
            ProfessionalBranch.objects.filter(professional=professional).delete()
            for branch in branches:
                ProfessionalBranch.objects.create(professional=professional, branch=branch)

        corte_norte, _ = Service.objects.update_or_create(salon=norte, name="Corte", defaults={"active": True})
        color_norte, _ = Service.objects.update_or_create(salon=norte, name="Color", defaults={"active": True})
        corte_sur, _ = Service.objects.update_or_create(salon=sur, name="Corte clásico", defaults={"active": True})
        for professional, services in [(sofia, [corte_norte, color_norte]), (diego, [corte_norte]), (vale, [corte_sur])]:
            ProfessionalService.objects.filter(professional=professional).delete()
            for service in services:
                ProfessionalService.objects.create(professional=professional, service=service)

        for branch, service, minutes in [(centro, corte_norte, 30), (centro, color_norte, 90), (pocitos, corte_norte, 40), (pocitos, color_norte, 100), (cordon, corte_sur, 35)]:
            BranchService.objects.update_or_create(branch=branch, service=service, defaults={"duration_minutes": minutes, "active": True})

        for professional, branch in [(sofia, pocitos), (diego, centro), (vale, cordon)]:
            for weekday in range(6):
                schedule, _ = WorkSchedule.objects.update_or_create(
                    professional=professional,
                    branch=branch,
                    weekday=weekday,
                    starts_at=time(9, 0),
                    defaults={"ends_at": time(18, 0)},
                )
                ScheduleBreak.objects.update_or_create(
                    schedule=schedule,
                    starts_at=time(13, 0),
                    defaults={"ends_at": time(14, 0)},
                )

        demo_day = timezone.localdate() + timedelta(days=1)
        while demo_day.weekday() == 6:
            demo_day += timedelta(days=1)
        demo_reservations = [
            (norte, centro, corte_norte, diego, "cliente.norte@example.test"),
            (sur, cordon, corte_sur, vale, "cliente.sur@example.test"),
        ]
        # Las reservas ya operadas (con auditoría o historial) se conservan; solo
        # se crea una nueva cuando no queda ninguna reserva demo próxima.
        for salon, branch, service, professional, email in demo_reservations:
            if Reservation.objects.filter(
                salon=salon, email=email, status=Reservation.Status.CONFIRMED, starts_at__gte=timezone.now(),
            ).exists():
                continue
            slots = available_slots(
                salon=salon,
                branch=branch,
                service=service,
                professional=professional,
                day=demo_day,
            )
            if slots:
                offering = BranchService.objects.get(branch=branch, service=service)
                Reservation.objects.create(
                    salon=salon,
                    branch=branch,
                    service=service,
                    professional=professional,
                    first_name="Cliente",
                    last_name="Demo",
                    email=email,
                    contact="099 000 000",
                    starts_at=slots[0],
                    ends_at=slots[0] + timedelta(minutes=offering.duration_minutes),
                    duration_minutes=offering.duration_minutes,
                    notes="Reserva creada por seed_demo para probar la agenda.",
                )

        RewardProgram.objects.update_or_create(
            salon=norte,
            defaults={
                "active": True,
                "services_required": 2,
                "period": RewardProgram.Period.MONTHLY,
                "discount_percent": 15,
            },
        )
        # Los servicios atendidos se crean una sola vez por día. Un canje ya
        # registrado es historial: no se borra para rehabilitar la recompensa.
        reward_email = "cliente.recompensa@example.test"
        local_tz = ZoneInfo(settings.TIME_ZONE)
        for hour in (7, 8):
            starts_at = timezone.make_aware(datetime.combine(timezone.localdate(), time(hour, 0)), local_tz)
            if Reservation.objects.filter(salon=norte, email=reward_email, starts_at=starts_at).exists():
                continue
            Reservation.objects.create(
                salon=norte,
                branch=centro,
                service=corte_norte,
                professional=diego,
                first_name="Cliente",
                last_name="Recompensa",
                email=reward_email,
                contact="099 555 555",
                starts_at=starts_at,
                ends_at=starts_at + timedelta(minutes=30),
                duration_minutes=30,
                status=Reservation.Status.COMPLETED,
                notes="Servicio atendido para demostrar el programa de recompensas.",
            )

        if not available_reward(norte, reward_email):
            self.stdout.write(self.style.WARNING(
                f"La recompensa demo de {reward_email} ya fue canjeada en el período actual; se conserva el canje."
            ))
        self.stdout.write(self.style.SUCCESS("Datos demo listos. Contraseña común: DemoTuTurno2026!"))

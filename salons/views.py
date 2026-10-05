import secrets
from urllib.parse import urlencode
from django.contrib import messages
from django.core import signing
from django.http import HttpResponseBadRequest
from .bulk_completion import managing_memberships, preview_completion, complete_preview
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from .access import (
    accessible_branches_for,
    accessible_reservations_for,
    active_memberships_for,
    can_manage_reservation,
    get_accessible_salon_or_404,
)
from .booking import available_slots
from .cancellation_policy import active_cancellation_booking_block
from accounts.email_delivery import EmailDeliveryError
from .email_delivery import send_guest_verification_email, send_reservation_confirmation_email
from .forms import (
    BookingForm,
    BookingLimitExceptionForm,
    BranchManagementForm,
    BranchServiceManagementForm,
    GuestStartForm,
    GuestVerifyForm,
    ProfessionalAbsenceForm,
    ProfessionalManagementForm,
    RewardProgramForm,
    RescheduleForm,
    SalonPolicyForm,
    ScheduleBreakForm,
    ServiceManagementForm,
    WorkScheduleForm,
)
from .models import BookingLimitException, Branch, BranchService, GuestVerification, HairSalon, Membership, Professional, ProfessionalAbsence, Reservation, ReservationReschedule, ReservationStatusChange, RewardProgram, RewardRedemption, ScheduleBreak, Service, WorkSchedule
from .rescheduling import RescheduleError, reschedule_reservation, slots_for_reservation
from .rewards import available_reward
from .reservation_status import change_reservation_status, reservation_actions


class BookingLimitReached(Exception):
    pass


class CancellationBookingBlockReached(Exception):
    def __init__(self, block):
        self.block = block


@login_required
def dashboard(request):
    memberships = active_memberships_for(request.user).prefetch_related("branches", "salon__branches")
    cards = [
        {"membership": membership, "branches": membership.authorized_branches()}
        for membership in memberships
    ]
    return render(request, "salons/dashboard.html", {"cards": cards})


@login_required
def salon_detail(request, slug):
    salon = get_accessible_salon_or_404(request.user, slug)
    branches = accessible_branches_for(request.user).filter(salon=salon).prefetch_related(
        "service_offerings__service", "professionals"
    )
    membership = active_memberships_for(request.user).get(salon=salon)
    template = "salons/_salon_detail.html" if request.headers.get("HX-Request") == "true" else "salons/salon_detail.html"
    return render(
        request,
        template,
        {
            "salon": salon,
            "branches": branches,
            "membership": membership,
            "can_configure": membership.role in {Membership.Role.OWNER, Membership.Role.ADMIN},
            "is_owner": membership.role == Membership.Role.OWNER,
        },
    )


@login_required
def salon_settings(request, slug):
    salon = get_accessible_salon_or_404(request.user, slug)
    membership = active_memberships_for(request.user).get(salon=salon)
    if membership.role not in {Membership.Role.OWNER, Membership.Role.ADMIN}:
        raise PermissionDenied
    form = SalonPolicyForm(request.POST or None, instance=salon)
    saved = False
    if request.method == "POST" and form.is_valid():
        form.save()
        saved = True
    return render(
        request,
        "salons/settings.html",
        {"salon": salon, "form": form, "saved": saved, "is_owner": membership.role == Membership.Role.OWNER},
    )


def _owner_salon_or_403(user, slug):
    salon = get_accessible_salon_or_404(user, slug)
    membership = active_memberships_for(user).get(salon=salon)
    if membership.role != Membership.Role.OWNER:
        raise PermissionDenied
    return salon


@login_required
def branch_management(request, slug, pk=None):
    salon = _owner_salon_or_403(request.user, slug)
    branch = get_object_or_404(Branch, salon=salon, pk=pk) if pk else None
    form = BranchManagementForm(request.POST or None, instance=branch, salon=salon)
    if request.method == "POST" and form.is_valid():
        saved_branch = form.save(commit=False)
        saved_branch.salon = salon
        saved_branch.save()
        return redirect("branch-management", slug=salon.slug)
    return render(
        request,
        "salons/branches.html",
        {"salon": salon, "form": form, "editing": branch, "branches": salon.branches.all()},
    )


@login_required
def service_management(request, slug):
    salon = _owner_salon_or_403(request.user, slug)
    form_type = request.POST.get("form_type") if request.method == "POST" else None
    service_form = ServiceManagementForm(
        request.POST if form_type == "service" else None,
        salon=salon,
        auto_id="service_%s",
    )
    offering_form = BranchServiceManagementForm(
        request.POST if form_type == "offering" else None,
        salon=salon,
        auto_id="offering_%s",
    )
    if form_type == "service" and service_form.is_valid():
        service = service_form.save(commit=False)
        service.salon = salon
        service.save()
        return redirect("service-management", slug=salon.slug)
    if form_type == "offering" and offering_form.is_valid():
        offering_form.save()
        return redirect("service-management", slug=salon.slug)
    services = salon.services.prefetch_related("branch_offerings__branch")
    return render(
        request,
        "salons/services.html",
        {
            "salon": salon,
            "service_form": service_form,
            "offering_form": offering_form,
            "services": services,
        },
    )


@login_required
def service_edit(request, slug, pk):
    salon = _owner_salon_or_403(request.user, slug)
    service = get_object_or_404(Service, salon=salon, pk=pk)
    form = ServiceManagementForm(request.POST or None, instance=service, salon=salon)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("service-management", slug=salon.slug)
    return render(
        request,
        "salons/catalog_edit.html",
        {"salon": salon, "form": form, "title": f"Editar {service.name}", "section": "Servicio", "cancel_url": reverse("service-management", args=[salon.slug])},
    )


@login_required
def offering_edit(request, slug, pk):
    salon = _owner_salon_or_403(request.user, slug)
    offering = get_object_or_404(BranchService, branch__salon=salon, service__salon=salon, pk=pk)
    form = BranchServiceManagementForm(request.POST or None, instance=offering, salon=salon)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("service-management", slug=salon.slug)
    return render(
        request,
        "salons/catalog_edit.html",
        {"salon": salon, "form": form, "title": f"Editar {offering.service.name} en {offering.branch.name}", "section": "Servicio por sucursal", "cancel_url": reverse("service-management", args=[salon.slug])},
    )


@login_required
def professional_management(request, slug, pk=None):
    salon = _owner_salon_or_403(request.user, slug)
    professional = get_object_or_404(Professional, salon=salon, pk=pk) if pk else None
    form = ProfessionalManagementForm(request.POST or None, instance=professional, salon=salon)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved_professional = form.save(commit=False)
            saved_professional.salon = salon
            saved_professional.save()
            saved_professional.branches.set(form.cleaned_data["branches"])
            saved_professional.services.set(form.cleaned_data["services"])
        return redirect("professional-management", slug=salon.slug)
    professionals = salon.professionals.prefetch_related("branches", "services")
    return render(
        request,
        "salons/professionals.html",
        {
            "salon": salon,
            "form": form,
            "editing": professional,
            "professionals": professionals,
        },
    )


@login_required
def booking_limit_exceptions(request, slug):
    salon = get_accessible_salon_or_404(request.user, slug)
    membership = active_memberships_for(request.user).get(salon=salon)
    if membership.role not in {Membership.Role.OWNER, Membership.Role.ADMIN}:
        raise PermissionDenied
    form = BookingLimitExceptionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        exception = form.save(commit=False)
        exception.salon = salon
        exception.created_by = request.user
        exception.save()
        return redirect("booking-limit-exceptions", slug=salon.slug)
    exceptions = salon.booking_limit_exceptions.select_related("created_by", "reservation")[:25]
    return render(
        request,
        "salons/booking_limit_exceptions.html",
        {"salon": salon, "form": form, "exceptions": exceptions},
    )


@login_required
def reward_settings(request, slug):
    salon = get_accessible_salon_or_404(request.user, slug)
    membership = active_memberships_for(request.user).get(salon=salon)
    if membership.role != Membership.Role.OWNER:
        raise PermissionDenied
    program, _ = RewardProgram.objects.get_or_create(salon=salon)
    form = RewardProgramForm(request.POST or None, instance=program)
    saved = False
    if request.method == "POST" and form.is_valid():
        form.save()
        saved = True
    recent_redemptions = salon.reward_redemptions.select_related("reservation")[:20]
    return render(
        request,
        "salons/rewards.html",
        {"salon": salon, "form": form, "saved": saved, "recent_redemptions": recent_redemptions},
    )


def _availability_scope(user, slug):
    salon = get_accessible_salon_or_404(user, slug)
    membership = active_memberships_for(user).get(salon=salon)
    if membership.role not in {Membership.Role.OWNER, Membership.Role.ADMIN}:
        raise PermissionDenied
    branches = accessible_branches_for(user).filter(salon=salon)
    return salon, branches


@login_required
def availability_settings(request, slug):
    salon, branches = _availability_scope(request.user, slug)
    form_type = request.POST.get("form_type") if request.method == "POST" else None
    schedule_form = WorkScheduleForm(
        request.POST if form_type == "schedule" else None,
        salon=salon,
        branches=branches,
    )
    break_form = ScheduleBreakForm(
        request.POST if form_type == "break" else None,
        salon=salon,
        branches=branches,
    )
    absence_form = ProfessionalAbsenceForm(
        request.POST if form_type == "absence" else None,
        salon=salon,
        branches=branches,
    )
    selected_form = {"schedule": schedule_form, "break": break_form, "absence": absence_form}.get(form_type)
    if selected_form and selected_form.is_valid():
        selected_form.save()
        return redirect("availability-settings", slug=salon.slug)
    schedules = WorkSchedule.objects.filter(branch__in=branches).select_related("professional", "branch").prefetch_related("breaks")
    absences = ProfessionalAbsence.objects.filter(branch__in=branches).select_related("professional", "branch")[:30]
    return render(
        request,
        "salons/availability.html",
        {
            "salon": salon,
            "schedule_form": schedule_form,
            "break_form": break_form,
            "absence_form": absence_form,
            "schedules": schedules,
            "absences": absences,
        },
    )


@login_required
def availability_delete(request, slug, kind, pk):
    if request.method != "POST":
        raise Http404
    salon, branches = _availability_scope(request.user, slug)
    if kind == "schedule":
        item = get_object_or_404(WorkSchedule, pk=pk, branch__in=branches, professional__salon=salon)
    elif kind == "break":
        item = get_object_or_404(ScheduleBreak, pk=pk, schedule__branch__in=branches, schedule__professional__salon=salon)
    elif kind == "absence":
        item = get_object_or_404(ProfessionalAbsence, pk=pk, branch__in=branches, professional__salon=salon)
    else:
        raise Http404
    item.delete()
    return redirect("availability-settings", slug=salon.slug)


@login_required
def agenda(request):
    try:
        selected_date = datetime.fromisoformat(request.GET.get("date", "")).date()
    except (TypeError, ValueError):
        selected_date = timezone.localdate()
    local_tz = ZoneInfo(settings.TIME_ZONE)
    day_start = timezone.make_aware(datetime.combine(selected_date, time.min), local_tz)
    day_end = day_start + timedelta(days=1)
    reservations = accessible_reservations_for(request.user).filter(starts_at__gte=day_start, starts_at__lt=day_end)
    branch_id = request.GET.get("branch")
    if branch_id:
        reservations = reservations.filter(branch_id=branch_id)
    items = [
        {"reservation": reservation, **reservation_actions(request.user, reservation)}
        for reservation in reservations.order_by("starts_at")
    ]
    context = {
        "items": items,
        "branches": accessible_branches_for(request.user).select_related("salon"),
        "selected_date": selected_date,
        "selected_branch": branch_id or "",
        "can_bulk_complete": managing_memberships(request.user).exists(),
    }
    template = "agenda/_results.html" if request.headers.get("HX-Request") == "true" else "agenda/index.html"
    return render(request, template, context)


@login_required
def reservation_status(request, pk):
    if request.method != "POST":
        raise Http404
    reservation = change_reservation_status(user=request.user, pk=pk, action=request.POST.get("action"))
    if request.headers.get("HX-Request") == "true":
        return render(
            request,
            "agenda/_reservation.html",
            {"reservation": reservation, **reservation_actions(request.user, reservation)},
        )
    reservation_date = timezone.localtime(reservation.starts_at).date().isoformat()
    return redirect(f"{reverse('agenda')}?date={reservation_date}")


def _reschedule_initial_day(reservation):
    reservation_day = timezone.localtime(reservation.starts_at).date()
    return max(reservation_day, timezone.localdate())


def _reschedule_form(request, reservation, *, source, changed_by=None):
    initial_day = _reschedule_initial_day(reservation)
    form = RescheduleForm(
        request.POST or None,
        initial={"date": initial_day} if request.method == "GET" else None,
    )
    updated = None
    if request.method == "POST" and form.is_valid():
        try:
            updated = reschedule_reservation(
                reservation=reservation,
                day=form.cleaned_data["date"],
                slot_value=form.cleaned_data["slot"],
                source=source,
                changed_by=changed_by,
                request=request,
            )
        except RescheduleError as error:
            form.add_error(error.field, str(error))
        except EmailDeliveryError:
            form.add_error(
                None,
                "No pudimos enviar la confirmación. La reserva conserva su horario anterior.",
            )
        except (IntegrityError, ValidationError):
            form.add_error("slot", "Ese horario acaba de ocuparse. Elegí otro.")
    selected_day = form.cleaned_data.get("date") if form.is_bound and "date" not in form.errors else initial_day
    slots = slots_for_reservation(reservation, selected_day) if selected_day else []
    return form, updated, slots


@login_required
def reservation_reschedule(request, pk):
    reservation = get_object_or_404(accessible_reservations_for(request.user), pk=pk)
    if not can_manage_reservation(request.user, reservation):
        raise PermissionDenied
    if reservation.status != Reservation.Status.CONFIRMED:
        raise PermissionDenied("La reserva ya no admite reprogramación.")
    form, updated, slots = _reschedule_form(
        request,
        reservation,
        source=ReservationReschedule.Source.SALON,
        changed_by=request.user,
    )
    if updated:
        reservation_day = timezone.localtime(updated.starts_at).date().isoformat()
        return redirect(f"{reverse('agenda')}?date={reservation_day}")
    return render(
        request,
        "booking/reschedule_form.html",
        {
            "reservation": reservation,
            "salon": reservation.salon,
            "form": form,
            "slots": slots,
            "slots_url": reverse("reservation-reschedule-slots", args=[reservation.id]),
            "back_url": f"{reverse('agenda')}?date={timezone.localtime(reservation.starts_at).date().isoformat()}",
            "staff_mode": True,
        },
    )


@login_required
def reservation_reschedule_slots(request, pk):
    reservation = get_object_or_404(accessible_reservations_for(request.user), pk=pk)
    if not can_manage_reservation(request.user, reservation):
        raise PermissionDenied
    try:
        day = datetime.fromisoformat(request.GET.get("date", "")).date()
    except (TypeError, ValueError):
        return render(request, "booking/_slots.html", {"slots": [], "incomplete": True})
    return render(request, "booking/_slots.html", {"slots": slots_for_reservation(reservation, day)})


def public_salon(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    branches = salon.branches.filter(active=True).prefetch_related("service_offerings__service", "professionals")
    return render(
        request,
        "booking/public_salon.html",
        {"salon": salon, "branches": branches, "guest": _verified_guest(request, salon)},
    )


def guest_start(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    form = GuestStartForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        code = f"{secrets.randbelow(1_000_000):06d}"
        email = form.cleaned_data["email"].lower()
        try:
            with transaction.atomic():
                verification = GuestVerification.objects.create(
                    email=email,
                    code_hash=make_password(code),
                    expires_at=timezone.now() + timedelta(minutes=15),
                )
                send_guest_verification_email(salon=salon, email=email, code=code)
        except EmailDeliveryError:
            request.session.pop("pending_guest", None)
            request.session.pop("debug_verification_code", None)
            form.add_error(
                None,
                "No pudimos enviar el código en este momento. Revisá el correo e intentá nuevamente.",
            )
        else:
            request.session["pending_guest"] = {
                "verification_id": verification.id,
                "salon_id": salon.id,
                "first_name": form.cleaned_data["first_name"],
                "last_name": form.cleaned_data["last_name"],
                "email": email,
                "contact": form.cleaned_data["contact"],
            }
            if settings.DEBUG:
                request.session["debug_verification_code"] = code
            return redirect("guest-verify", slug=salon.slug)
    return render(request, "booking/guest_start.html", {"salon": salon, "form": form})


def guest_verify(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    pending = request.session.get("pending_guest")
    if not pending or pending.get("salon_id") != salon.id:
        return redirect("guest-start", slug=salon.slug)
    verification = get_object_or_404(GuestVerification, id=pending.get("verification_id"), email=pending.get("email"))
    form = GuestVerifyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        verification.attempts += 1
        if verification.is_valid and check_password(form.cleaned_data["code"], verification.code_hash):
            verification.verified_at = timezone.now()
            verification.save(update_fields=["attempts", "verified_at"])
            request.session["verified_guest"] = {
                "salon_id": salon.id,
                "first_name": pending["first_name"],
                "last_name": pending["last_name"],
                "email": pending["email"],
                "contact": pending["contact"],
                "verified_at": timezone.now().isoformat(),
            }
            request.session.pop("pending_guest", None)
            request.session.pop("debug_verification_code", None)
            return redirect("booking-create", slug=salon.slug)
        verification.save(update_fields=["attempts"])
        form.add_error("code", "El código es incorrecto, venció o superó el máximo de intentos.")
    return render(
        request,
        "booking/guest_verify.html",
        {"salon": salon, "form": form, "email": pending["email"], "debug_code": request.session.get("debug_verification_code") if settings.DEBUG else None},
    )


def _verified_guest(request, salon):
    guest = request.session.get("verified_guest")
    if not guest or guest.get("salon_id") != salon.id:
        return None
    try:
        verified_at = datetime.fromisoformat(guest["verified_at"])
    except (KeyError, TypeError, ValueError):
        return None
    if verified_at < timezone.now() - timedelta(hours=24):
        return None
    return guest


def guest_logout(request, slug):
    if request.method != "POST":
        raise Http404
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    verified_guest = request.session.get("verified_guest")
    if verified_guest and verified_guest.get("salon_id") == salon.id:
        request.session.pop("verified_guest", None)
        request.session.pop("last_reservation_id", None)
    pending_guest = request.session.get("pending_guest")
    if pending_guest and pending_guest.get("salon_id") == salon.id:
        request.session.pop("pending_guest", None)
        request.session.pop("debug_verification_code", None)
    return redirect("public-salon", slug=salon.slug)


def my_reservations(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    guest = _verified_guest(request, salon)
    if not guest:
        return redirect("guest-start", slug=salon.slug)
    reservations = Reservation.objects.filter(
        salon=salon,
        email__iexact=guest["email"],
    ).select_related("branch", "service", "professional").order_by("-starts_at")
    return render(
        request,
        "booking/my_reservations.html",
        {"salon": salon, "guest": guest, "reservations": reservations},
    )


def booking_create(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    guest = _verified_guest(request, salon)
    if not guest:
        return redirect("guest-start", slug=salon.slug)
    cancellation_block = active_cancellation_booking_block(
        salon=salon,
        customer_email=guest["email"],
    )
    initial_date = timezone.localdate() + timedelta(days=1)
    active_weekdays = set(
        WorkSchedule.objects.filter(professional__salon=salon).values_list("weekday", flat=True)
    )
    for _ in range(7):
        if initial_date.weekday() in active_weekdays:
            break
        initial_date += timedelta(days=1)
    form = BookingForm(
        request.POST or None,
        salon=salon,
        initial={"date": initial_date} if request.method == "GET" else None,
    )
    if request.method == "POST" and form.is_valid():
        branch = form.cleaned_data["branch"]
        service = form.cleaned_data["service"]
        professional = form.cleaned_data["professional"]
        day = form.cleaned_data["date"]
        slots = available_slots(salon=salon, branch=branch, service=service, professional=professional, day=day)
        selected = next((slot for slot in slots if slot.isoformat() == form.cleaned_data["slot"]), None)
        if not selected:
            form.add_error("slot", "Ese horario ya no está disponible. Elegí otro.")
        else:
            offering = BranchService.objects.get(branch=branch, service=service, active=True)
            try:
                with transaction.atomic():
                    HairSalon.objects.select_for_update().get(pk=salon.pk)
                    cancellation_block = active_cancellation_booking_block(
                        salon=salon,
                        customer_email=guest["email"],
                    )
                    if cancellation_block:
                        raise CancellationBookingBlockReached(cancellation_block)
                    local_tz = ZoneInfo(settings.TIME_ZONE)
                    day_start = timezone.make_aware(datetime.combine(day, time.min), local_tz)
                    day_end = day_start + timedelta(days=1)
                    active_count = Reservation.objects.filter(
                        salon=salon,
                        email__iexact=guest["email"],
                        status=Reservation.Status.CONFIRMED,
                        starts_at__gte=day_start,
                        starts_at__lt=day_end,
                    ).count()
                    limit_exception = None
                    if active_count >= 5:
                        limit_exception = BookingLimitException.objects.select_for_update().filter(
                            salon=salon,
                            customer_email__iexact=guest["email"],
                            booking_date=day,
                            used_at__isnull=True,
                        ).first()
                        if not limit_exception:
                            raise BookingLimitReached
                    reward = available_reward(salon, guest["email"])
                    reservation = Reservation.objects.create(
                        salon=salon,
                        branch=branch,
                        service=service,
                        professional=professional,
                        first_name=guest["first_name"],
                        last_name=guest["last_name"],
                        email=guest["email"],
                        contact=guest["contact"],
                        starts_at=selected,
                        ends_at=selected + timedelta(minutes=offering.duration_minutes),
                        duration_minutes=offering.duration_minutes,
                        cancellation_notice_hours=salon.cancellation_notice_hours,
                        reward_discount_percent=reward["program"].discount_percent if reward else 0,
                        notes=form.cleaned_data["notes"],
                    )
                    if limit_exception:
                        limit_exception.reservation = reservation
                        limit_exception.used_at = timezone.now()
                        limit_exception.save(update_fields=["reservation", "used_at"])
                    if reward:
                        RewardRedemption.objects.create(
                            salon=salon,
                            customer_email=guest["email"],
                            period_start=reward["period_start"],
                            period_end=reward["period_end"],
                            attended_services=reward["attended"],
                            discount_percent=reward["program"].discount_percent,
                            reservation=reservation,
                        )
                    send_reservation_confirmation_email(request=request, reservation=reservation)
            except CancellationBookingBlockReached as error:
                cancellation_block = error.block
            except BookingLimitReached:
                form.add_error(None, "Ya tenés cinco reservas activas para esa fecha en esta peluquería.")
            except EmailDeliveryError:
                form.add_error(
                    None,
                    "No pudimos enviar la confirmación. La reserva no fue creada; intentá nuevamente.",
                )
            except (IntegrityError, ValidationError):
                form.add_error("slot", "El horario acaba de ocuparse. Elegí otro.")
            else:
                request.session["last_reservation_id"] = reservation.id
                return redirect("booking-success", slug=salon.slug)
    return render(
        request,
        "booking/booking_form.html",
        {
            "salon": salon,
            "guest": guest,
            "form": form,
            "reward": available_reward(salon, guest["email"]),
            "cancellation_block": cancellation_block,
        },
    )


def booking_slots(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    if not _verified_guest(request, salon):
        raise Http404
    try:
        branch = salon.branches.get(id=request.GET.get("branch"), active=True)
        service = salon.services.get(id=request.GET.get("service"), active=True)
        professional = salon.professionals.get(id=request.GET.get("professional"), active=True)
        day = datetime.fromisoformat(request.GET.get("date", "")).date()
    except (Branch.DoesNotExist, Service.DoesNotExist, Professional.DoesNotExist, TypeError, ValueError):
        return render(request, "booking/_slots.html", {"slots": [], "incomplete": True})
    slots = available_slots(salon=salon, branch=branch, service=service, professional=professional, day=day)
    return render(request, "booking/_slots.html", {"slots": slots})


def booking_success(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    guest = _verified_guest(request, salon)
    reservation_id = request.session.get("last_reservation_id")
    if not guest or not reservation_id:
        return redirect("public-salon", slug=salon.slug)
    reservation = get_object_or_404(Reservation, id=reservation_id, salon=salon, email=guest["email"])
    return render(
        request,
        "booking/success.html",
        {"salon": salon, "guest": guest, "reservation": reservation},
    )


def client_cancel(request, slug, token):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    reservation = get_object_or_404(
        Reservation.objects.select_related("branch", "service", "professional"),
        salon=salon,
        cancellation_token=token,
    )
    cancelled_now = False
    if request.method == "POST" and reservation.can_client_cancel:
        with transaction.atomic():
            HairSalon.objects.select_for_update().get(pk=salon.pk)
            reservation = Reservation.objects.select_for_update().select_related(
                "branch", "service", "professional"
            ).get(pk=reservation.pk)
            if reservation.can_client_cancel:
                reservation.status = Reservation.Status.CANCELLED_CLIENT
                reservation.cancelled_at = timezone.now()
                reservation.save(update_fields=["status", "cancelled_at"])
                ReservationStatusChange.objects.create(
                    reservation=reservation, previous_status=Reservation.Status.CONFIRMED,
                    new_status=Reservation.Status.CANCELLED_CLIENT,
                )
                cancelled_now = True
    return render(
        request,
        "booking/cancel.html",
        {
            "salon": salon,
            "reservation": reservation,
            "cancelled_now": cancelled_now,
            "rescheduled_now": request.GET.get("reprogramada") == "1",
        },
    )


def client_reschedule(request, slug, token):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    reservation = get_object_or_404(
        Reservation.objects.select_related("salon", "branch", "service", "professional"),
        salon=salon,
        cancellation_token=token,
    )
    if not reservation.can_client_reschedule:
        return render(
            request,
            "booking/reschedule_form.html",
            {"salon": salon, "reservation": reservation, "unavailable": True, "staff_mode": False},
        )
    form, updated, slots = _reschedule_form(
        request,
        reservation,
        source=ReservationReschedule.Source.CLIENT,
    )
    if updated:
        return redirect(f"{reverse('client-cancel', args=[salon.slug, reservation.cancellation_token])}?reprogramada=1")
    return render(
        request,
        "booking/reschedule_form.html",
        {
            "salon": salon,
            "reservation": reservation,
            "form": form,
            "slots": slots,
            "slots_url": reverse("client-reschedule-slots", args=[salon.slug, reservation.cancellation_token]),
            "back_url": reverse("client-cancel", args=[salon.slug, reservation.cancellation_token]),
            "staff_mode": False,
        },
    )


def client_reschedule_slots(request, slug, token):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    reservation = get_object_or_404(
        Reservation.objects.select_related("salon", "branch", "service", "professional"),
        salon=salon,
        cancellation_token=token,
    )
    if not reservation.can_client_reschedule:
        raise Http404
    try:
        day = datetime.fromisoformat(request.GET.get("date", "")).date()
    except (TypeError, ValueError):
        return render(request, "booking/_slots.html", {"slots": [], "incomplete": True})
    return render(request, "booking/_slots.html", {"slots": slots_for_reservation(reservation, day)})


@login_required
def reservation_bulk_complete(request):
    if not managing_memberships(request.user).exists():
        raise PermissionDenied
    if request.method == 'POST':
        try:
            day, branch, count = complete_preview(request.user, request.POST.get('token', ''))
        except (signing.BadSignature, ValueError, TypeError, KeyError):
            return HttpResponseBadRequest('Confirmación inválida o vencida. Volvé a la agenda.')
        messages.success(request, f'Se marcaron {count} reservas como atendidas.' if count else 'No hay reservas finalizadas pendientes de marcar como atendidas.')
        query = urlencode({'date': day.isoformat(), 'branch': branch.pk if branch else ''})
        return redirect(reverse('agenda') + '?' + query)
    if request.method != 'GET':
        raise Http404
    try:
        day, branch, count, token = preview_completion(request.user, request.GET.get('date', ''), request.GET.get('branch', ''))
    except (ValueError, TypeError):
        return HttpResponseBadRequest('Fecha o sucursal inválida.')
    return render(request, 'agenda/bulk_confirm.html', {'day': day, 'branch': branch, 'count': count, 'token': token})

import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from .access import (
    accessible_branches_for,
    accessible_reservations_for,
    active_memberships_for,
    can_complete_reservation,
    can_manage_reservation,
    get_accessible_salon_or_404,
)
from .booking import available_slots
from .forms import BookingForm, BookingLimitExceptionForm, GuestStartForm, GuestVerifyForm, SalonPolicyForm
from .models import BookingLimitException, Branch, BranchService, GuestVerification, HairSalon, Membership, Professional, Reservation, Service, WorkSchedule


class BookingLimitReached(Exception):
    pass


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
    return render(request, "salons/settings.html", {"salon": salon, "form": form, "saved": saved})


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
        {
            "reservation": reservation,
            "can_cancel": reservation.status == Reservation.Status.CONFIRMED and can_manage_reservation(request.user, reservation),
            "can_complete": reservation.status == Reservation.Status.CONFIRMED and can_complete_reservation(request.user, reservation),
        }
        for reservation in reservations.order_by("starts_at")
    ]
    context = {
        "items": items,
        "branches": accessible_branches_for(request.user).select_related("salon"),
        "selected_date": selected_date,
        "selected_branch": branch_id or "",
    }
    template = "agenda/_results.html" if request.headers.get("HX-Request") == "true" else "agenda/index.html"
    return render(request, template, context)


@login_required
def reservation_status(request, pk):
    if request.method != "POST":
        raise Http404
    reservation = get_object_or_404(accessible_reservations_for(request.user), pk=pk)
    action = request.POST.get("action")
    if reservation.status != Reservation.Status.CONFIRMED:
        raise PermissionDenied("La reserva ya no admite cambios.")
    if action == "cancel":
        if not can_manage_reservation(request.user, reservation):
            raise PermissionDenied
        reservation.status = Reservation.Status.CANCELLED_SALON
    elif action == "complete":
        if not can_complete_reservation(request.user, reservation):
            raise PermissionDenied
        reservation.status = Reservation.Status.COMPLETED
    else:
        raise Http404
    reservation.save(update_fields=["status"])
    if request.headers.get("HX-Request") == "true":
        return render(
            request,
            "agenda/_reservation.html",
            {"reservation": reservation, "can_cancel": False, "can_complete": False},
        )
    reservation_date = timezone.localtime(reservation.starts_at).date().isoformat()
    return redirect(f"{reverse('agenda')}?date={reservation_date}")


def public_salon(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    branches = salon.branches.filter(active=True).prefetch_related("service_offerings__service", "professionals")
    return render(request, "booking/public_salon.html", {"salon": salon, "branches": branches})


def guest_start(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    form = GuestStartForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        code = f"{secrets.randbelow(1_000_000):06d}"
        verification = GuestVerification.objects.create(
            email=form.cleaned_data["email"].lower(),
            code_hash=make_password(code),
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        request.session["pending_guest"] = {
            "verification_id": verification.id,
            "salon_id": salon.id,
            "first_name": form.cleaned_data["first_name"],
            "last_name": form.cleaned_data["last_name"],
            "email": form.cleaned_data["email"].lower(),
            "contact": form.cleaned_data["contact"],
        }
        send_mail(
            "Tu código para reservar en TuTurnoUy",
            f"Tu código de verificación es {code}. Vence en 15 minutos.",
            settings.DEFAULT_FROM_EMAIL,
            [form.cleaned_data["email"]],
        )
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


def booking_create(request, slug):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    guest = _verified_guest(request, salon)
    if not guest:
        return redirect("guest-start", slug=salon.slug)
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
                        notes=form.cleaned_data["notes"],
                    )
                    if limit_exception:
                        limit_exception.reservation = reservation
                        limit_exception.used_at = timezone.now()
                        limit_exception.save(update_fields=["reservation", "used_at"])
            except BookingLimitReached:
                form.add_error(None, "Ya tenés cinco reservas activas para esa fecha en esta peluquería.")
            except (IntegrityError, ValidationError):
                form.add_error("slot", "El horario acaba de ocuparse. Elegí otro.")
            else:
                request.session["last_reservation_id"] = reservation.id
                cancellation_url = request.build_absolute_uri(
                    reverse("client-cancel", args=[salon.slug, reservation.cancellation_token])
                )
                send_mail(
                    f"Reserva confirmada en {salon.name}",
                    (
                        f"Tu reserva quedó confirmada para {timezone.localtime(reservation.starts_at):%d/%m/%Y a las %H:%M}.\n"
                        f"Podés consultar o cancelar la reserva en: {cancellation_url}"
                    ),
                    settings.DEFAULT_FROM_EMAIL,
                    [reservation.email],
                )
                return redirect("booking-success", slug=salon.slug)
    return render(request, "booking/booking_form.html", {"salon": salon, "guest": guest, "form": form})


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
    return render(request, "booking/success.html", {"salon": salon, "reservation": reservation})


def client_cancel(request, slug, token):
    salon = get_object_or_404(HairSalon.objects.filter(active=True), slug=slug)
    reservation = get_object_or_404(
        Reservation.objects.select_related("branch", "service", "professional"),
        salon=salon,
        cancellation_token=token,
    )
    cancelled_now = False
    if request.method == "POST" and reservation.can_client_cancel:
        reservation.status = Reservation.Status.CANCELLED_CLIENT
        reservation.save(update_fields=["status"])
        cancelled_now = True
    return render(
        request,
        "booking/cancel.html",
        {"salon": salon, "reservation": reservation, "cancelled_now": cancelled_now},
    )

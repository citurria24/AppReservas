import json
from datetime import date, datetime, time, timedelta
from functools import wraps

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils import timezone

from .access import active_memberships_for, accessible_branches_for, accessible_reservations_for
from .bulk_completion import managing_memberships, preview_completion, complete_preview
from .models import Branch, Membership
from .reservation_status import change_reservation_status, reservation_actions
from .statistics_views import owner_report


def api_view(method):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({'error': 'La sesión venció. Ingresá nuevamente.'}, status=401)
            if request.method != method:
                response = JsonResponse({'error': 'Método no permitido.'}, status=405)
                response['Allow'] = method
                return response
            try:
                response = view(request, *args, **kwargs)
            except Http404:
                response = JsonResponse({'error': 'No se encontró el recurso.'}, status=404)
            except PermissionDenied:
                response = JsonResponse({'error': 'No tenés permisos para acceder a esta sección.'}, status=403)
            except (ValueError, TypeError, KeyError, ValidationError, signing.BadSignature):
                response = JsonResponse({'error': 'Datos inválidos o confirmación vencida. Volvé a intentar.'}, status=400)
            response['Cache-Control'] = 'private, no-store'
            return response
        return wrapped
    return decorator


def body(request):
    if request.content_type != 'application/json':
        raise ValueError('Se requiere JSON')
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError('Se requiere un objeto')
    return data


def branch_data(branch):
    return {'id': branch.pk, 'name': branch.name, 'salon': branch.salon.slug}


@api_view('GET')
def me(request):
    memberships = list(active_memberships_for(request.user).order_by('pk'))
    requested = request.GET.get('salon')
    current = next((m for m in memberships if m.salon.slug == requested), None) if requested else next(iter(memberships), None)
    if requested and current is None:
        raise Http404
    salons = [{'id': m.salon_id, 'name': m.salon.name, 'slug': m.salon.slug, 'role': m.role} for m in memberships]
    return JsonResponse({
        'id': request.user.pk, 'username': request.user.username,
        'display_name': request.user.get_full_name() or request.user.username,
        'role': current.role if current else None, 'salon': next((s for s in salons if current and s['id'] == current.salon_id), None),
        'salons': salons,
        'branches': [branch_data(b) for b in accessible_branches_for(request.user).select_related('salon')],
        'permissions': {'bulk_complete': managing_memberships(request.user).exists(), 'statistics': any(m.role == Membership.Role.OWNER for m in memberships)},
        'csrf_token': get_token(request), 'login_url': reverse('login'), 'logout_url': reverse('logout'),
        'today': timezone.localdate().isoformat(),
    })


@api_view('GET')
def agenda(request):
    day = date.fromisoformat(request.GET.get('date') or timezone.localdate().isoformat())
    if day.year >= 9999:
        raise ValueError('Fecha fuera de rango')
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    reservations = accessible_reservations_for(request.user).filter(starts_at__gte=start, starts_at__lt=end)
    branch_id = request.GET.get('branch')
    branches = accessible_branches_for(request.user).select_related('salon')
    if branch_id:
        branch = branches.filter(pk=int(branch_id)).first()
        if not branch:
            raise Http404
        reservations = reservations.filter(branch=branch)
    items = []
    action_names = {'can_complete': 'mark_attended', 'can_no_show': 'mark_absent', 'can_cancel': 'cancel_local', 'can_reschedule': 'reschedule'}
    for r in reservations.order_by('starts_at', 'pk'):
        actions = [action_names[key] for key, allowed in reservation_actions(request.user, r).items() if allowed]
        starts, ends = timezone.localtime(r.starts_at), timezone.localtime(r.ends_at)
        items.append({'id': r.pk, 'date': starts.date().isoformat(), 'starts_at': starts.isoformat(), 'ends_at': ends.isoformat(),
                      'start_time': starts.strftime('%H:%M'), 'end_time': ends.strftime('%H:%M'),
                      'salon': {'name': r.salon.name, 'slug': r.salon.slug}, 'branch': branch_data(r.branch),
                      'professional': {'id': r.professional_id, 'name': r.professional.display_name},
                      'service': {'id': r.service_id, 'name': r.service.name},
                      'client': f'{r.first_name} {r.last_name}', 'email': r.email, 'phone': r.contact,
                      'notes': r.notes, 'status': r.status, 'status_label': r.get_status_display(),
                      'allowed_actions': actions,
                      'reschedule_url': reverse('reservation-reschedule', args=[r.pk]) if 'reschedule' in actions else None})
    return JsonResponse({'date': day.isoformat(), 'branches': [branch_data(b) for b in branches], 'reservations': items,
                         'can_bulk_complete': managing_memberships(request.user).exists(),
                         'summary': {'total': len(items), 'attended': sum(r['status'] == 'completed' for r in items),
                                     'absent': sum(r['status'] == 'no_show' for r in items), 'confirmed': sum(r['status'] == 'confirmed' for r in items)}})


@api_view('POST')
def reservation_action(request, pk):
    actions = {'mark_attended': 'complete', 'mark_absent': 'no_show', 'cancel_local': 'cancel'}
    action = actions.get(body(request).get('action'))
    if not action:
        raise ValueError('Acción inválida')
    reservation = change_reservation_status(user=request.user, pk=pk, action=action)
    return JsonResponse({'id': reservation.pk, 'status': reservation.status, 'message': 'Reserva actualizada.'})


@api_view('POST')
def bulk_preview(request):
    data = body(request)
    day, branch, count, token = preview_completion(request.user, data.get('date', ''), data.get('branch', ''))
    return JsonResponse({'date': day.isoformat(), 'branch': branch.pk if branch else None, 'count': count, 'token': token})


@api_view('POST')
def bulk_execute(request):
    if not managing_memberships(request.user).exists():
        raise PermissionDenied
    day, branch, count = complete_preview(request.user, body(request).get('token', ''))
    return JsonResponse({'date': day.isoformat(), 'branch': branch.pk if branch else None, 'count': count,
                         'message': f'Se marcaron {count} reservas como atendidas.' if count else 'No hay reservas finalizadas pendientes de marcar como atendidas.'})


@api_view('GET')
def statistics(request, slug):
    salon, form, report = owner_report(request, slug)
    if report is None:
        return JsonResponse({'error': 'Revisá los filtros seleccionados.', 'fields': form.errors.get_json_data()}, status=400)
    s = report['summary']
    distribution = [{'status': status, 'label': label, 'count': count} for status, label, count in [
        ('completed', 'Atendidas', s['attended']), ('no_show', 'Ausentes', s['absent']),
        ('cancelled_client', 'Canceladas por cliente', s['cancelled_client']), ('cancelled_salon', 'Canceladas por local', s['cancelled_salon']),
        ('confirmed', 'Confirmadas', s['total'] - s['attended'] - s['absent'] - s['cancelled_client'] - s['cancelled_salon']),
    ] if count]
    return JsonResponse({'salon': {'name': salon.name, 'slug': salon.slug}, 'month': report['month'], 'year': report['year'],
                         'branch': report['branch'].pk if report['branch'] else None,
                         'branches': [branch_data(b) for b in Branch.objects.filter(salon=salon).select_related('salon').order_by('name')],
                         'summary': s, 'by_branch': report['groups']['branch'], 'by_professional': report['groups']['professional'],
                         'by_service': report['groups']['service'], 'distribution': distribution,
                         'export_url': reverse('statistics-export', args=[salon.slug])})

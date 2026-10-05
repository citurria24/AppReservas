from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET

from .access import active_memberships_for, get_accessible_salon_or_404
from .models import Membership
from .statistics import StatisticsFilterForm, monthly_report, report_workbook


def owner_report(request, slug):
    salon = get_accessible_salon_or_404(request.user, slug)
    if not active_memberships_for(request.user).filter(salon=salon, role=Membership.Role.OWNER).exists():
        raise PermissionDenied
    now = timezone.localdate()
    data = request.GET.copy()
    if 'month' not in data:
        data['month'] = now.month
    if 'year' not in data:
        data['year'] = now.year
    form = StatisticsFilterForm(data, salon=salon)
    if not form.is_valid():
        return salon, form, None
    return salon, form, monthly_report(salon, **form.cleaned_data)


@login_required
@require_GET
def statistics(request, slug):
    salon, form, report = owner_report(request, slug)
    filters = urlencode(form.cleaned_data | {'branch': form.cleaned_data['branch'].pk if form.cleaned_data.get('branch') else ''}) if report else ''
    return render(request, 'salons/statistics.html', {'salon': salon, 'form': form, 'report': report, 'export_filters': filters}, status=200 if report else 400)


@login_required
@require_GET
def statistics_export(request, slug):
    salon, form, report = owner_report(request, slug)
    if report is None:
        return render(request, 'salons/statistics.html', {'salon': salon, 'form': form}, status=400)
    branch_name = '_' + (slugify(report['branch'].name) or 'sucursal') if report['branch'] else ''
    filename = f"TuTurnoUy_{salon.slug}_{report['year']:04d}-{report['month']:02d}{branch_name}.xlsx"
    response = FileResponse(report_workbook(report), as_attachment=True, filename=filename,
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Cache-Control'] = 'private, no-store'
    return response

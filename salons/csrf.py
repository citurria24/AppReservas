from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure


def csrf_failure(request, reason=''):
    if request.path.startswith('/api/'):
        return JsonResponse({'error': 'La verificación de seguridad venció. Recargá la página e intentá nuevamente.'}, status=403)
    return django_csrf_failure(request, reason=reason)

from django.urls import path
from . import api_views

urlpatterns = [
    path('me/', api_views.me, name='api-me'),
    path('agenda/', api_views.agenda, name='api-agenda'),
    path('reservas/<int:pk>/acciones/', api_views.reservation_action, name='api-reservation-action'),
    path('agenda/marcado-masivo/preview/', api_views.bulk_preview, name='api-bulk-preview'),
    path('agenda/marcado-masivo/ejecutar/', api_views.bulk_execute, name='api-bulk-execute'),
    path('peluquerias/<slug:slug>/estadisticas/', api_views.statistics, name='api-statistics'),
]

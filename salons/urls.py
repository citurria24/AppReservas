from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("peluquerias/<slug:slug>/", views.salon_detail, name="salon-detail"),
    path("peluquerias/<slug:slug>/configuracion/", views.salon_settings, name="salon-settings"),
    path("peluquerias/<slug:slug>/excepciones/", views.booking_limit_exceptions, name="booking-limit-exceptions"),
    path("peluquerias/<slug:slug>/recompensas/", views.reward_settings, name="reward-settings"),
    path("peluquerias/<slug:slug>/disponibilidad/", views.availability_settings, name="availability-settings"),
    path("peluquerias/<slug:slug>/disponibilidad/<str:kind>/<int:pk>/eliminar/", views.availability_delete, name="availability-delete"),
    path("agenda/", views.agenda, name="agenda"),
    path("agenda/reservas/<int:pk>/estado/", views.reservation_status, name="reservation-status"),
    path("reservar/<slug:slug>/", views.public_salon, name="public-salon"),
    path("reservar/<slug:slug>/invitado/", views.guest_start, name="guest-start"),
    path("reservar/<slug:slug>/verificar/", views.guest_verify, name="guest-verify"),
    path("reservar/<slug:slug>/turno/", views.booking_create, name="booking-create"),
    path("reservar/<slug:slug>/horarios/", views.booking_slots, name="booking-slots"),
    path("reservar/<slug:slug>/confirmada/", views.booking_success, name="booking-success"),
    path("reservar/<slug:slug>/cancelar/<uuid:token>/", views.client_cancel, name="client-cancel"),
]

from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("peluquerias/<slug:slug>/", views.salon_detail, name="salon-detail"),
    path("reservar/<slug:slug>/", views.public_salon, name="public-salon"),
    path("reservar/<slug:slug>/invitado/", views.guest_start, name="guest-start"),
    path("reservar/<slug:slug>/verificar/", views.guest_verify, name="guest-verify"),
    path("reservar/<slug:slug>/turno/", views.booking_create, name="booking-create"),
    path("reservar/<slug:slug>/horarios/", views.booking_slots, name="booking-slots"),
    path("reservar/<slug:slug>/confirmada/", views.booking_success, name="booking-success"),
]

from django.contrib import admin
from .models import (
    Branch,
    BranchService,
    BookingLimitException,
    HairSalon,
    Membership,
    MembershipBranch,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    ProfessionalAbsence,
    Reservation,
    ReservationReschedule,
    ReservationStatusChange,
    RewardProgram,
    RewardRedemption,
    ScheduleBreak,
    Service,
    WorkSchedule,
    GuestVerification,
)


class BranchInline(admin.TabularInline):
    model = Branch
    extra = 0


@admin.register(HairSalon)
class HairSalonAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "active")
    list_filter = ("active",)
    search_fields = ("name", "slug")
    inlines = (BranchInline,)


admin.site.register(Branch)
admin.site.register(Membership)
admin.site.register(MembershipBranch)
admin.site.register(Professional)
admin.site.register(ProfessionalBranch)
admin.site.register(ProfessionalService)
admin.site.register(Service)
admin.site.register(BranchService)
admin.site.register(WorkSchedule)
admin.site.register(ScheduleBreak)
admin.site.register(ProfessionalAbsence)
admin.site.register(GuestVerification)
admin.site.register(Reservation)
admin.site.register(ReservationReschedule)
admin.site.register(BookingLimitException)
admin.site.register(RewardProgram)
admin.site.register(RewardRedemption)
admin.site.site_header = "TuTurnoUy · Administración técnica"


@admin.register(ReservationStatusChange)
class ReservationStatusChangeAdmin(admin.ModelAdmin):
    list_display = ("reservation", "previous_status", "new_status", "changed_by", "created_at")
    readonly_fields = ("reservation", "previous_status", "new_status", "changed_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

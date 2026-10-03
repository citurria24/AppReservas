from django.contrib import admin
from .models import (
    Branch,
    BranchService,
    HairSalon,
    Membership,
    MembershipBranch,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    ProfessionalAbsence,
    Reservation,
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
admin.site.site_header = "TuTurnoUy · Administración técnica"

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import StudentInvite, User


# ── Custom admin action ───────────────────────────────────────────────────────

@admin.action(description='Seçili koçları onayla (is_approved + is_active = True)')
def approve_coaches(modeladmin, request, queryset):
    queryset.filter(role='coach').update(is_approved=True, is_active=True)


# ── User admin ────────────────────────────────────────────────────────────────

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ('full_name', 'email', 'role', 'is_approved', 'is_active', 'created_at')
    list_filter   = ('role', 'is_active', 'is_approved')
    search_fields = ('full_name', 'email')
    ordering      = ('full_name',)
    actions       = [approve_coaches]

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Kişisel Bilgiler', {'fields': ('full_name', 'role')}),
        ('İzinler', {'fields': ('is_active', 'is_approved', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    _coach_fieldset = ('Koç Ataması', {'fields': ('coach',)})

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj and obj.role == 'student':
            return fieldsets + (self._coach_fieldset,)
        return fieldsets

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'role', 'password1', 'password2'),
        }),
    )


# ── StudentInvite admin ───────────────────────────────────────────────────────

@admin.register(StudentInvite)
class StudentInviteAdmin(admin.ModelAdmin):
    list_display   = ('email', 'full_name', 'coach', 'is_used', 'created_at')
    list_filter    = ('is_used', 'coach')
    search_fields  = ('email', 'full_name', 'coach__full_name')
    readonly_fields = ('token', 'created_at')

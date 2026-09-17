from datetime import date

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import CoachStudent, StudentInvite, User


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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.role == 'student' and obj.coach_id and 'coach' in form.changed_data:
            CoachStudent.objects.get_or_create(
                coach_id=obj.coach_id,
                student=obj,
                defaults={'active': True, 'source': CoachStudent.SOURCE_VAGUS},
            )


# ── StudentInvite admin ───────────────────────────────────────────────────────

@admin.register(StudentInvite)
class StudentInviteAdmin(admin.ModelAdmin):
    list_display   = ('email', 'full_name', 'coach', 'is_used', 'created_at')
    list_filter    = ('is_used', 'coach')
    search_fields  = ('email', 'full_name', 'coach__full_name')
    readonly_fields = ('token', 'created_at')


# ── CoachStudent admin ────────────────────────────────────────────────────────

class SourceFilter(admin.SimpleListFilter):
    title = 'Kaynak'
    parameter_name = 'source'

    def lookups(self, request, model_admin):
        return [
            ('vagus',         'Vagus'),
            ('coach',         'Koç'),
            ('unclassified',  'Belirsiz'),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'vagus':
            return queryset.filter(source='vagus')
        if self.value() == 'coach':
            return queryset.filter(source='coach')
        if self.value() == 'unclassified':
            return queryset.filter(source__isnull=True)
        return queryset


@admin.register(CoachStudent)
class CoachStudentAdmin(admin.ModelAdmin):
    list_display   = ('coach', 'student', 'source', 'next_payment_due', 'days_remaining_col', 'active', 'created_at')
    list_editable  = ('source', 'next_payment_due')
    list_filter    = (SourceFilter, 'active', 'coach')
    search_fields  = ('coach__full_name', 'student__full_name')
    readonly_fields = ('created_at',)

    @admin.display(description='Kalan Gün')
    def days_remaining_col(self, obj):
        if obj.next_payment_due is None:
            return '—'
        days = (obj.next_payment_due - date.today()).days
        if days < 0:
            return f'Gecikmiş ({abs(days)} gün)'
        if days <= 7:
            return f'⚠ {days} gün'
        return f'{days} gün'

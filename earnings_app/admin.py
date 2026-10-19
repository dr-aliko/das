from django.contrib import admin

from .models import EarningConfig, EarningRow, ManualPaymentRecord


@admin.register(ManualPaymentRecord)
class ManualPaymentRecordAdmin(admin.ModelAdmin):
    list_display = ['pk', 'student', 'coach', 'amount_kurus', 'coach_pool_kurus', 'date', 'days', 'created_by', 'created_at']
    list_filter = ['coach', 'date']
    search_fields = ['student__email', 'student__full_name', 'coach__email']
    raw_id_fields = ['student', 'coach', 'created_by']
    date_hierarchy = 'created_at'


@admin.register(EarningRow)
class EarningRowAdmin(admin.ModelAdmin):
    list_display = ['pk', 'coach', 'student', 'coverage_start', 'coverage_end',
                    'pool_kurus', 'amount_kurus', 'kind', 'status', 'gap_fallback']
    list_filter = ['status', 'kind', 'gap_fallback', 'coach']
    search_fields = ['coach__email', 'student__email', 'order__pk']
    raw_id_fields = ['coach', 'student', 'order', 'manual_record',
                     'approved_by', 'paid_by', 'voided_by']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at']


@admin.register(EarningConfig)
class EarningConfigAdmin(admin.ModelAdmin):
    list_display = ['pk', 'provider_commission_pct', 'tax_pct']

    def has_add_permission(self, request):
        return not EarningConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

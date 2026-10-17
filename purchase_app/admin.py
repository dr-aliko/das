from django.contrib import admin

from .models import Order, Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display  = ('name', 'kind', 'price_kurus', 'duration_days', 'active', 'created_at')
    list_editable = ('active',)
    list_filter   = ('kind', 'active')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = ('pk', 'email', 'coach', 'plan', 'amount_kurus', 'status', 'provider', 'created_at')
    list_filter   = ('status', 'provider', 'plan')
    search_fields = ('email', 'full_name', 'provider_ref')
    readonly_fields = ('token', 'provider_ref', 'amount_kurus', 'created_at', 'updated_at')
    raw_id_fields = ('student', 'coach')

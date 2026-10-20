from django.contrib import admin
from .models import CapacitySettings, CoachCapacityGrant, CoachCapacityOrder


@admin.register(CapacitySettings)
class CapacitySettingsAdmin(admin.ModelAdmin):
    list_display = ['per_slot_price_kurus', 'updated_at']


@admin.register(CoachCapacityOrder)
class CoachCapacityOrderAdmin(admin.ModelAdmin):
    list_display = ['pk', 'coach', 'slots', 'amount_kurus', 'status', 'ref_code', 'created_at']
    list_filter = ['status']
    search_fields = ['coach__full_name', 'coach__email', 'ref_code']
    raw_id_fields = ['coach']


@admin.register(CoachCapacityGrant)
class CoachCapacityGrantAdmin(admin.ModelAdmin):
    list_display = ['pk', 'coach', 'slots', 'period_start', 'period_end', 'order']
    list_filter = ['period_end']
    search_fields = ['coach__full_name', 'coach__email']
    raw_id_fields = ['coach', 'order']

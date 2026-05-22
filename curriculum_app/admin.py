from django.contrib import admin

from .models import MacroPlan, MacroPlanBucket, MacroPlanTopic


class MacroPlanTopicInline(admin.TabularInline):
    model = MacroPlanTopic
    fields = ['topic', 'order']
    extra = 0
    raw_id_fields = ['topic']


class MacroPlanBucketInline(admin.TabularInline):
    model = MacroPlanBucket
    fields = ['label', 'start_date', 'end_date', 'order']
    extra = 0
    show_change_link = True


@admin.register(MacroPlan)
class MacroPlanAdmin(admin.ModelAdmin):
    list_display   = ['coach', 'student', 'sinav_tipi', 'target_date', 'algorithm', 'created_at', 'total_topics']
    list_filter    = ['sinav_tipi', 'algorithm']
    search_fields  = ['coach__full_name', 'student__full_name', 'title']
    inlines        = [MacroPlanBucketInline]
    raw_id_fields  = ['coach', 'student']


@admin.register(MacroPlanBucket)
class MacroPlanBucketAdmin(admin.ModelAdmin):
    list_display = ['plan', 'label', 'start_date', 'end_date', 'order', 'topic_count']
    inlines      = [MacroPlanTopicInline]

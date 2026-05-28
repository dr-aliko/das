from django.contrib import admin

from .models import (
    MacroPlan, MacroPlanBucket, MacroPlanTopic, MacroPlanSkippedTopic,
    MacroPlanWeekBucket, MacroPlanWeekTopic, PlanningRule, PlanRiskAlert,
)


class MacroPlanTopicInline(admin.TabularInline):
    model = MacroPlanTopic
    fields = ['topic', 'order', 'is_manual']
    extra = 0
    raw_id_fields = ['topic']


class MacroPlanSkippedTopicInline(admin.TabularInline):
    model = MacroPlanSkippedTopic
    fields = ['topic', 'reason', 'created_at']
    readonly_fields = ['created_at']
    extra = 0
    raw_id_fields = ['topic']


class MacroPlanBucketInline(admin.TabularInline):
    model = MacroPlanBucket
    fields = ['label', 'start_date', 'end_date', 'order']
    extra = 0
    show_change_link = True


class PlanRiskAlertInline(admin.TabularInline):
    model = PlanRiskAlert
    fields = ['kind', 'severity', 'message', 'is_dismissed']
    extra = 0
    readonly_fields = ['kind', 'severity', 'message']


@admin.register(MacroPlan)
class MacroPlanAdmin(admin.ModelAdmin):
    list_display   = ['coach', 'student', 'sinav_tipi', 'target_date', 'algorithm', 'status', 'segment',
                      'planning_mode', 'tyt_start_date', 'ayt_start_date', 'created_at', 'total_topics']
    list_filter    = ['sinav_tipi', 'algorithm', 'status', 'planning_mode']
    search_fields  = ['coach__full_name', 'student__full_name', 'title']
    inlines        = [MacroPlanBucketInline, MacroPlanSkippedTopicInline, PlanRiskAlertInline]
    raw_id_fields  = ['coach', 'student']


@admin.register(MacroPlanBucket)
class MacroPlanBucketAdmin(admin.ModelAdmin):
    list_display = ['plan', 'label', 'start_date', 'end_date', 'order', 'window_kind', 'topic_count']
    list_filter  = ['window_kind']
    inlines      = [MacroPlanTopicInline]


@admin.register(MacroPlanWeekTopic)
class MacroPlanWeekTopicAdmin(admin.ModelAdmin):
    list_display  = ['week', 'topic', 'activity', 'hours', 'reason']
    list_filter   = ['activity']
    raw_id_fields = ['week', 'topic']


@admin.register(PlanningRule)
class PlanningRuleAdmin(admin.ModelAdmin):
    list_display = ['coach', 'rule_key', 'value', 'updated_at']
    list_filter  = ['rule_key']
    raw_id_fields = ['coach']


@admin.register(MacroPlanSkippedTopic)
class MacroPlanSkippedTopicAdmin(admin.ModelAdmin):
    list_display  = ['plan', 'topic', 'reason', 'created_at']
    list_filter   = ['reason']
    search_fields = ['plan__student__full_name', 'topic__name']
    raw_id_fields = ['plan', 'topic']


@admin.register(PlanRiskAlert)
class PlanRiskAlertAdmin(admin.ModelAdmin):
    list_display  = ['plan', 'kind', 'severity', 'is_dismissed', 'created_at']
    list_filter   = ['severity', 'kind', 'is_dismissed']
    search_fields = ['plan__title', 'message']

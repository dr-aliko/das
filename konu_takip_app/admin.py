from django.contrib import admin
from .models import KonuTakipTopic, StudentTopicProgress


class ChildTopicInline(admin.TabularInline):
    model = KonuTakipTopic
    fk_name = 'parent'
    extra = 0
    fields = ('name', 'order', 'checkable')


@admin.register(KonuTakipTopic)
class KonuTakipTopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'parent', 'order', 'checkable')
    list_filter = ('subject', 'checkable')
    search_fields = ('name',)
    inlines = [ChildTopicInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('subject', 'parent')


@admin.register(StudentTopicProgress)
class StudentTopicProgressAdmin(admin.ModelAdmin):
    list_display = ('student', 'topic', 'started', 'finished', 'started_at', 'finished_at')
    list_filter = ('started', 'finished')
    search_fields = ('student__full_name', 'topic__name')
    raw_id_fields = ('student', 'topic')

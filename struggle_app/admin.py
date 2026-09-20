from django.contrib import admin

from .models import StudentStruggleQuestion


@admin.register(StudentStruggleQuestion)
class StudentStruggleQuestionAdmin(admin.ModelAdmin):
    list_display  = ('id', 'student', 'subject', 'topic', 'review_count', 'next_review_at', 'created_at')
    list_filter   = ('subject',)
    search_fields = ('student__email', 'student__full_name', 'subject__name')
    raw_id_fields = ('student', 'subject', 'topic')
    readonly_fields = ('created_at', 'last_reviewed_at')

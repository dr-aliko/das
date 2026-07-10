from django.contrib import admin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin
from .models import (
    Publisher, Subject, Topic, Exam, ExamResult, ExamTopicError,
    BransDeneme, BransTopicError,
    PlacementExam, ExamQuestion, StudentExamAttempt, StudentQuestionAnswer,
)


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


class TopicInline(admin.TabularInline):
    model = Topic
    extra = 3


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'exam_type')
    list_filter = ('exam_type',)
    inlines = [TopicInline]


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display   = ('name', 'subject', 'sub_category', 'priority_tag', 'is_baglayici', 'yield_score', 'expected_hours')
    list_filter    = ('subject__exam_type', 'subject', 'priority_tag', 'is_baglayici')
    search_fields  = ('name',)
    filter_horizontal = ('depends_on',)


class ExamResultInline(admin.TabularInline):
    model = ExamResult
    extra = 0
    readonly_fields = ('net_score',)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('custom_name', 'student', 'publisher', 'exam_date', 'total_net')
    list_filter = ('publisher', 'exam_date')
    search_fields = ('custom_name', 'student__full_name')
    inlines = [ExamResultInline]


@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ('exam', 'subject', 'correct_answers', 'wrong_answers', 'blank_answers', 'net_score')
    readonly_fields = ('net_score',)


@admin.register(ExamTopicError)
class ExamTopicErrorAdmin(admin.ModelAdmin):
    list_display = ('exam', 'topic', 'wrong_count', 'blank_count')
    list_filter = ('topic__subject',)


# ── BransDeneme admin ─────────────────────────────────────────────────────────

class BransTopicErrorInline(admin.TabularInline):
    model = BransTopicError
    extra = 0
    readonly_fields = ('topic',)


@admin.register(BransDeneme)
class BransDenemeAdmin(admin.ModelAdmin):
    list_display = ('student', 'ders', 'tarih', 'dogru', 'yanlis', 'bos', 'net')
    list_filter = ('ders__exam_type', 'ders', 'tarih')
    search_fields = ('student__full_name',)
    readonly_fields = ('net',)
    inlines = [BransTopicErrorInline]


@admin.register(BransTopicError)
class BransTopicErrorAdmin(admin.ModelAdmin):
    list_display = ('brans_deneme', 'topic', 'yanlis_sayisi')
    list_filter = ('topic__subject', 'brans_deneme__ders')
    search_fields = ('brans_deneme__student__full_name', 'topic__name')
    readonly_fields = ('brans_deneme', 'topic')


# ── Seviye Tespit Sınavı admin ────────────────────────────────────────────────

class ExamQuestionInline(admin.StackedInline):
    model = ExamQuestion
    extra = 1
    fields = (
        ('subject', 'topic', 'order'),
        'question_text',
        'question_image',
        ('option_a', 'option_b'),
        ('option_c', 'option_d'),
        ('option_e', 'correct_option'),
    )


@admin.register(PlacementExam)
class PlacementExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'duration_minutes', 'question_count', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title',)
    inlines = [ExamQuestionInline]


class ExamQuestionResource(resources.ModelResource):
    exam = fields.Field(
        column_name='exam_id',
        attribute='exam',
        widget=ForeignKeyWidget(PlacementExam, 'pk'),
    )

    class Meta:
        model = ExamQuestion
        fields = (
            'id', 'exam', 'order', 'subject', 'topic',
            'question_text', 'question_image',
            'option_a', 'option_b', 'option_c', 'option_d', 'option_e',
            'correct_option',
        )
        import_id_fields = ('id',)
        skip_unchanged = True
        report_skipped = False


@admin.register(ExamQuestion)
class ExamQuestionAdmin(ImportExportModelAdmin):
    resource_classes = [ExamQuestionResource]
    list_display = ('exam', 'order', 'subject', 'correct_option', 'topic')
    list_filter = ('exam', 'subject', 'correct_option')
    search_fields = ('question_text', 'topic')


class StudentQuestionAnswerInline(admin.TabularInline):
    model = StudentQuestionAnswer
    extra = 0
    readonly_fields = ('question', 'selected_option', 'is_correct')


@admin.register(StudentExamAttempt)
class StudentExamAttemptAdmin(admin.ModelAdmin):
    list_display = ('student', 'exam', 'is_completed', 'correct_count', 'wrong_count',
                    'blank_count', 'net_score', 'start_time')
    list_filter = ('exam', 'is_completed')
    search_fields = ('student__full_name',)
    readonly_fields = ('start_time', 'net_score')
    inlines = [StudentQuestionAnswerInline]

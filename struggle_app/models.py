import os
import uuid
from datetime import date as _date

from django.conf import settings
from django.db import models


def _struggle_q_upload(instance, filename):
    ext = os.path.splitext(filename)[1]
    today = _date.today()
    return f"struggle/questions/{today.year}/{today.month:02d}/{uuid.uuid4().hex}{ext}"


def _struggle_s_upload(instance, filename):
    ext = os.path.splitext(filename)[1]
    today = _date.today()
    return f"struggle/solutions/{today.year}/{today.month:02d}/{uuid.uuid4().hex}{ext}"


class StudentStruggleQuestion(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='struggle_questions',
    )
    subject = models.ForeignKey(
        'exams_app.Subject',
        on_delete=models.CASCADE,
        related_name='struggle_questions',
    )
    topic = models.ForeignKey(
        'konu_takip_app.KonuTakipTopic',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='struggle_questions',
    )
    question_image = models.ImageField(
        upload_to=_struggle_q_upload, blank=True, null=True,
    )
    question_text = models.TextField(blank=True)
    solution_image = models.ImageField(
        upload_to=_struggle_s_upload, blank=True, null=True,
    )
    solution_text = models.TextField(blank=True)
    notes     = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Spaced-repetition state — same five fields as StudentTopicProgress.
    # New questions start immediately due: caller sets next_review_at=timezone.now().
    next_review_at        = models.DateTimeField(null=True, blank=True)
    last_reviewed_at      = models.DateTimeField(null=True, blank=True)
    current_interval_days = models.PositiveIntegerField(default=1)
    ease_factor           = models.FloatField(default=2.5)
    review_count          = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Zorlandığım Soru'
        verbose_name_plural = 'Zorlandığım Sorular'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student} — {self.subject.name} #{self.pk}'

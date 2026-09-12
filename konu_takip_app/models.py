from django.conf import settings
from django.db import models


class KonuTakipTopic(models.Model):
    subject = models.ForeignKey(
        'exams_app.Subject',
        on_delete=models.CASCADE,
        related_name='konu_takip_topics',
    )
    name = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)
    # Nullable: root-level topics have parent=None; children point to their header.
    parent = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='children',
    )
    # False for category headers (e.g. "Problemler") — not directly checkable.
    checkable = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Konu'
        verbose_name_plural = 'Konular'
        ordering = ['subject', 'order']

    def __str__(self):
        if self.parent:
            return f'{self.subject.name} / {self.parent.name} → {self.name}'
        return f'{self.subject.name} → {self.name}'


class StudentTopicProgress(models.Model):
    topic = models.ForeignKey(
        KonuTakipTopic,
        on_delete=models.CASCADE,
        related_name='progress_entries',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='konu_takip_progress',
    )
    started = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    finished = models.BooleanField(default=False)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Öğrenci Konu İlerlemesi'
        verbose_name_plural = 'Öğrenci Konu İlerlemeleri'
        unique_together = [('topic', 'student')]

    def __str__(self):
        return f'{self.student} — {self.topic.name}'

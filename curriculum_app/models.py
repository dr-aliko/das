from django.conf import settings
from django.db import models


class MacroPlan(models.Model):
    SINAV_TYT  = 'TYT'
    SINAV_AYT  = 'AYT'
    SINAV_BOTH = 'BOTH'
    SINAV_CHOICES = [('TYT', 'TYT'), ('AYT', 'AYT'), ('BOTH', 'TYT + AYT')]

    ALGO_EVEN     = 'even'
    ALGO_WEAKNESS = 'weighted_weakness'
    ALGO_CHOICES  = [
        ('even',             'Eşit Dağılım'),
        ('weighted_weakness', 'Zayıf Konulara Ağırlık'),
    ]

    coach      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='macro_plans', limit_choices_to={'role': 'coach'},
    )
    student    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='macro_plans_as_student', limit_choices_to={'role': 'student'},
    )
    sinav_tipi  = models.CharField(max_length=4, choices=SINAV_CHOICES, default='TYT')
    target_date = models.DateField(help_text='Snapshot of the student exam date at plan creation time.')
    algorithm   = models.CharField(max_length=20, choices=ALGO_CHOICES, default='even')
    title       = models.CharField(max_length=200, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    regenerated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Makro Plan'
        verbose_name_plural = 'Makro Planlar'

    def __str__(self):
        return f'{self.student.full_name} — {self.get_sinav_tipi_display()} ({self.target_date})'

    @property
    def months_remaining(self):
        from datetime import date
        today = date.today()
        if self.target_date <= today:
            return 0
        return (self.target_date.year - today.year) * 12 + self.target_date.month - today.month

    @property
    def total_topics(self):
        return MacroPlanTopic.objects.filter(bucket__plan=self).count()


class MacroPlanBucket(models.Model):
    plan       = models.ForeignKey(MacroPlan, on_delete=models.CASCADE, related_name='buckets')
    label      = models.CharField(max_length=60)  # e.g. "Eylül 2025"
    start_date = models.DateField()
    end_date   = models.DateField()
    order      = models.PositiveSmallIntegerField()  # 0-indexed month offset

    class Meta:
        unique_together = ['plan', 'order']
        ordering = ['order']
        verbose_name = 'Plan Ayı'
        verbose_name_plural = 'Plan Ayları'

    def __str__(self):
        return f'{self.plan} / {self.label}'

    @property
    def topic_count(self):
        return self.topics.count()


class MacroPlanTopic(models.Model):
    bucket = models.ForeignKey(MacroPlanBucket, on_delete=models.CASCADE, related_name='topics')
    topic  = models.ForeignKey(
        'exams_app.Topic', on_delete=models.CASCADE, related_name='macro_plan_entries',
    )
    order  = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ['bucket', 'topic']
        ordering = ['order']
        verbose_name = 'Plan Konusu'
        verbose_name_plural = 'Plan Konuları'

    def __str__(self):
        return f'{self.bucket.label} → {self.topic.name}'

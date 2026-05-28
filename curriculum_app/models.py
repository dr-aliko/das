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

    STATUS_DRAFT    = 'DRAFT'
    STATUS_APPROVED = 'APPROVED'
    STATUS_CHOICES  = [('DRAFT', 'Taslak'), ('APPROVED', 'Onaylandı')]

    MODE_BACKWARD = 'EXAM_DATE_BACKWARD'
    MODE_CUSTOM   = 'CUSTOM_WINDOWS'
    MODE_CHOICES  = [
        ('EXAM_DATE_BACKWARD', 'Sınav Tarihinden Geri Sayım'),
        ('CUSTOM_WINDOWS',     'Özel Tarih Aralıkları'),
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
    status      = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    # segment: cached result of determine_segment() — e.g. 'starter', 'mid', 'advanced'
    segment     = models.CharField(max_length=30, blank=True, default='')
    planning_mode  = models.CharField(max_length=25, choices=MODE_CHOICES, default='EXAM_DATE_BACKWARD')
    tyt_start_date = models.DateField(null=True, blank=True)
    tyt_end_date   = models.DateField(null=True, blank=True)
    ayt_start_date = models.DateField(null=True, blank=True)
    ayt_end_date   = models.DateField(null=True, blank=True)
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
    WINDOW_TYT  = 'TYT'
    WINDOW_AYT  = 'AYT'
    WINDOW_BOTH = 'BOTH'
    WINDOW_CHOICES = [('TYT', 'TYT'), ('AYT', 'AYT'), ('BOTH', 'TYT + AYT')]

    plan        = models.ForeignKey(MacroPlan, on_delete=models.CASCADE, related_name='buckets')
    label       = models.CharField(max_length=60)  # e.g. "Eylül 2025"
    start_date  = models.DateField()
    end_date    = models.DateField()
    order       = models.PositiveSmallIntegerField()  # 0-indexed month offset
    window_kind = models.CharField(max_length=4, choices=WINDOW_CHOICES, default='BOTH', db_index=True)

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
    bucket    = models.ForeignKey(MacroPlanBucket, on_delete=models.CASCADE, related_name='topics')
    topic     = models.ForeignKey(
        'exams_app.Topic', on_delete=models.CASCADE, related_name='macro_plan_entries',
    )
    order     = models.PositiveSmallIntegerField(default=0)
    is_manual = models.BooleanField(default=False, db_index=True)

    class Meta:
        unique_together = ['bucket', 'topic']
        ordering = ['order']
        verbose_name = 'Plan Konusu'
        verbose_name_plural = 'Plan Konuları'

    def __str__(self):
        return f'{self.bucket.label} → {self.topic.name}'


class MacroPlanSkippedTopic(models.Model):
    """Topics marked 'Halledilmiş / Gerek Yok' by the coach in the editor."""
    plan      = models.ForeignKey(MacroPlan, on_delete=models.CASCADE, related_name='skipped_topics')
    topic     = models.ForeignKey('exams_app.Topic', on_delete=models.CASCADE, related_name='plan_skips')
    reason    = models.CharField(max_length=120, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['plan', 'topic']
        verbose_name = 'Atlanan Konu'
        verbose_name_plural = 'Atlanan Konular'

    def __str__(self):
        return f'{self.plan} / atlanan: {self.topic.name}'


class MacroPlanWeekBucket(models.Model):
    """Weekly subdivision of a MacroPlanBucket (week_index 0-3)."""
    bucket     = models.ForeignKey(MacroPlanBucket, on_delete=models.CASCADE, related_name='weeks')
    week_index = models.PositiveSmallIntegerField()  # 0 = first week of the month
    # Activity mix percentages (must sum to 100 per row, not enforced at DB level)
    pct_new_topic  = models.PositiveSmallIntegerField(default=60, verbose_name='Yeni Konu %')
    pct_revision   = models.PositiveSmallIntegerField(default=25, verbose_name='Tekrar %')
    pct_trial      = models.PositiveSmallIntegerField(default=15, verbose_name='Deneme %')

    class Meta:
        unique_together = ['bucket', 'week_index']
        ordering = ['bucket', 'week_index']
        verbose_name = 'Haftalık Dilim'
        verbose_name_plural = 'Haftalık Dilimler'

    def __str__(self):
        return f'{self.bucket.label} / Hafta {self.week_index + 1}'


class MacroPlanWeekTopic(models.Model):
    """Concrete topic assignment within a MacroPlanWeekBucket."""
    ACTIVITY_NEW      = 'new'
    ACTIVITY_REVISION = 'revision'
    ACTIVITY_REPAIR   = 'repair'
    ACTIVITY_TRIAL    = 'trial'
    ACTIVITY_CHOICES = [
        ('new',      'Yeni Konu'),
        ('revision', 'Tekrar'),
        ('repair',   'Zayıf Konu Onarımı'),
        ('trial',    'Deneme / Karışık'),
    ]

    week     = models.ForeignKey(MacroPlanWeekBucket, on_delete=models.CASCADE, related_name='topics')
    topic    = models.ForeignKey(
        'exams_app.Topic', on_delete=models.CASCADE, related_name='week_assignments',
    )
    hours    = models.PositiveSmallIntegerField(default=3, verbose_name='Hedef Saat')
    activity = models.CharField(max_length=10, choices=ACTIVITY_CHOICES, default='new', db_index=True)
    reason   = models.CharField(max_length=200, blank=True, default='')
    order    = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ['week', 'topic']
        ordering = ['week', 'order']
        verbose_name = 'Haftalık Konu Görevi'
        verbose_name_plural = 'Haftalık Konu Görevleri'

    def __str__(self):
        return f'{self.week} → {self.topic.name} ({self.get_activity_display()})'


class PlanningRule(models.Model):
    """Coach-scoped default overrides for engine parameters."""
    RULE_TYT_RATIO       = 'tyt_ratio'
    RULE_YIELD_THRESHOLD = 'yield_threshold'
    RULE_CHOICES = [
        ('tyt_ratio',       'TYT Oranı (0.0-1.0)'),
        ('yield_threshold', 'Düşük Verim Eşiği'),
    ]

    coach      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='planning_rules', limit_choices_to={'role': 'coach'},
    )
    rule_key   = models.CharField(max_length=30, choices=RULE_CHOICES)
    value      = models.CharField(max_length=50, help_text='Parsed by engine as float/int.')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['coach', 'rule_key']
        verbose_name = 'Planlama Kuralı'
        verbose_name_plural = 'Planlama Kuralları'

    def __str__(self):
        return f'{self.coach.email} / {self.rule_key} = {self.value}'


class PlanRiskAlert(models.Model):
    """Curriculum-local risk flags generated by risk_engine.py for a MacroPlan."""
    SEVERITY_INFO    = 'INFO'
    SEVERITY_WARNING = 'WARNING'
    SEVERITY_CRITICAL = 'CRITICAL'
    SEVERITY_CHOICES = [
        ('INFO',     'Bilgi'),
        ('WARNING',  'Uyarı'),
        ('CRITICAL', 'Kritik'),
    ]

    RISK_AHMET        = 'ahmet_syndrome'
    RISK_EA_VERBAL    = 'ea_verbal_delay'
    RISK_BAGLAYICI    = 'baglayici_skipped'
    RISK_TIME_CRUNCH  = 'time_crunch'
    RISK_OVERLOAD     = 'overload'
    RISK_OTHER        = 'other'
    RISK_KIND_CHOICES = [
        ('ahmet_syndrome',   'Ahmet Sendromu (TYT ihmali)'),
        ('ea_verbal_delay',  'EA Sozel Gecikmesi'),
        ('baglayici_skipped', 'Baglayici Konu Atlandi'),
        ('time_crunch',      'Yetersiz Sure'),
        ('overload',         'Asiri Yuk'),
        ('other',            'Diger'),
    ]

    plan       = models.ForeignKey(MacroPlan, on_delete=models.CASCADE, related_name='risk_alerts')
    kind       = models.CharField(max_length=25, choices=RISK_KIND_CHOICES)
    severity   = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='WARNING')
    message    = models.TextField()
    is_dismissed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-severity', 'kind']
        verbose_name = 'Risk Uyarısı'
        verbose_name_plural = 'Risk Uyarıları'

    def __str__(self):
        return f'[{self.severity}] {self.plan} — {self.kind}'

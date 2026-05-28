from django.conf import settings
from django.db import models


class Publisher(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = 'Yayın'
        verbose_name_plural = 'Yayınlar'
        ordering = ['name']

    def __str__(self):
        return self.name


class Subject(models.Model):
    EXAM_TYPE_CHOICES = [('TYT', 'TYT'), ('AYT', 'AYT')]

    exam_type = models.CharField(max_length=3, choices=EXAM_TYPE_CHOICES, default='TYT')
    name = models.CharField(max_length=100)
    question_count = models.PositiveSmallIntegerField(default=40)
    excluded_from_planning = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Ders'
        verbose_name_plural = 'Dersler'
        ordering = ['exam_type', 'name']
        unique_together = [('exam_type', 'name')]

    @property
    def display_name(self):
        prefix = f'{self.exam_type} '
        return self.name[len(prefix):] if self.name.startswith(prefix) else self.name

    def __str__(self):
        return f'{self.exam_type} - {self.name}'


class Topic(models.Model):
    PRIORITY_CORE        = 'CORE'
    PRIORITY_INDEPENDENT = 'INDEPENDENT'
    PRIORITY_OPTIONAL    = 'OPTIONAL'
    PRIORITY_CHOICES = [
        ('CORE',        'Temel (Zorunlu)'),
        ('INDEPENDENT', 'Bağımsız'),
        ('OPTIONAL',    'Opsiyonel'),
    ]

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='topics')
    name = models.CharField(max_length=200)
    # Sosyal → Tarih/Coğrafya/Felsefe/Din Kültürü  |  Fen → Fizik/Kimya/Biyoloji
    sub_category = models.CharField(max_length=100, blank=True, default='')

    # ── Curriculum planning metadata ──────────────────────────────────────────
    # is_baglayici: topic unlocks dependent topics (prerequisite)
    is_baglayici  = models.BooleanField(default=False, verbose_name='Bağlayıcı Konu')
    # expected_hours: nominal study hours needed to reach competency
    expected_hours = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Beklenen Çalışma Saati',
    )
    # yield_score: 0-100, higher = more exam questions per study hour
    yield_score   = models.PositiveSmallIntegerField(
        default=50, verbose_name='Verim Skoru (0-100)',
    )
    priority_tag  = models.CharField(
        max_length=12, choices=PRIORITY_CHOICES, default=PRIORITY_CORE,
        verbose_name='Öncelik',
    )
    # depends_on: topics that must be studied before this one
    depends_on    = models.ManyToManyField(
        'self', symmetrical=False, blank=True,
        related_name='unlocks', verbose_name='Ön Koşul Konular',
    )
    excluded_from_planning = models.BooleanField(default=False)
    order_index = models.PositiveSmallIntegerField(
        default=9999, verbose_name='Pedagojik Sıra',
        help_text='Konu havuzunda gösterim sırası. Küçük = önce. 9999 = sırasız.',
    )

    class Meta:
        verbose_name = 'Konu'
        verbose_name_plural = 'Konular'
        ordering = ['subject', 'order_index', 'sub_category', 'name']
        unique_together = [('subject', 'name')]

    def __str__(self):
        if self.sub_category:
            return f'{self.subject.name} / {self.sub_category} → {self.name}'
        return f'{self.subject.name} → {self.name}'


class Exam(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exams',
        limit_choices_to={'role': 'student'},
    )
    publisher = models.ForeignKey(Publisher, on_delete=models.PROTECT, related_name='exams')
    custom_name = models.CharField(max_length=200)
    exam_date = models.DateField()
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    student_note = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Deneme'
        verbose_name_plural = 'Denemeler'
        ordering = ['-exam_date', '-created_at']
        indexes = [models.Index(fields=['student', 'exam_date'])]

    def __str__(self):
        return f'{self.student.full_name} — {self.custom_name} ({self.exam_date})'

    def total_net(self):
        return sum(r.net_score for r in self.results.all())


class ExamResult(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='results')
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='results')
    correct_answers = models.PositiveSmallIntegerField(default=0)
    wrong_answers = models.PositiveSmallIntegerField(default=0)
    blank_answers = models.PositiveSmallIntegerField(default=0)
    subject_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    net_score = models.FloatField(default=0)

    class Meta:
        verbose_name = 'Sonuç'
        verbose_name_plural = 'Sonuçlar'
        unique_together = [('exam', 'subject')]

    def __str__(self):
        return f'{self.exam} / {self.subject.name}: {self.net_score}'

    def save(self, *args, **kwargs):
        self.net_score = round(self.correct_answers - (self.wrong_answers * 0.25), 2)
        super().save(*args, **kwargs)

    def has_errors(self):
        return self.wrong_answers > 0 or self.blank_answers > 0


class ExamTopicError(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='topic_errors')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='errors')
    wrong_count = models.PositiveSmallIntegerField(default=0)
    blank_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Konu Hatası'
        verbose_name_plural = 'Konu Hataları'
        unique_together = [('exam', 'topic')]
        indexes = [models.Index(fields=['exam', 'topic'])]

    def __str__(self):
        return f'{self.topic.name}: {self.wrong_count}Y {self.blank_count}B'

    def total_errors(self):
        return self.wrong_count + self.blank_count


class StudentTask(models.Model):
    SOURCE_TRIAL  = 'trial'
    SOURCE_BRANCH = 'branch'
    SOURCE_CHOICES = [('trial', 'Trial'), ('branch', 'Branch')]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks',
        limit_choices_to={'role': 'student'},
    )
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='tasks')
    task_source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, default='trial', db_index=True,
    )
    assigned_by_coach = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # SM-2 Spaced Repetition
    repetition_count = models.IntegerField(default=0)
    easiness_factor = models.FloatField(default=2.5)
    interval_days = models.IntegerField(default=0)
    next_review_date = models.DateField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Görev'
        verbose_name_plural = 'Görevler'
        unique_together = [('student', 'topic', 'task_source')]

    def __str__(self):
        status = '✓' if self.is_completed else '○'
        return f'{status} {self.student.full_name} → {self.topic.name}'


# ── Branş Deneme — completely independent from the main Exam system ───────────

class BransDeneme(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='brans_denemeler',
        limit_choices_to={'role': 'student'},
    )
    ders = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='brans_denemeler',
        verbose_name='Ders',
    )
    tarih  = models.DateField(verbose_name='Tarih')
    dogru  = models.PositiveSmallIntegerField(default=0, verbose_name='Doğru')
    yanlis = models.PositiveSmallIntegerField(default=0, verbose_name='Yanlış')
    bos    = models.PositiveSmallIntegerField(default=0, verbose_name='Boş')
    net          = models.FloatField(default=0, verbose_name='Net', editable=False)
    sure_dakika  = models.PositiveIntegerField(null=True, blank=True, verbose_name='Süre (dk)')
    ogrenci_notu = models.TextField(blank=True, default='', verbose_name='Not')
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Branş Deneme'
        verbose_name_plural = 'Branş Denemeler'
        ordering = ['-tarih', '-olusturulma_tarihi']
        indexes = [models.Index(fields=['student', 'ders', 'tarih'])]

    def save(self, *args, **kwargs):
        self.net = round(self.dogru - self.yanlis * 0.25, 2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.student.full_name} — {self.ders.name} — {self.tarih}'


class BransTopicError(models.Model):
    brans_deneme  = models.ForeignKey(
        BransDeneme,
        on_delete=models.CASCADE,
        related_name='topic_errors',
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name='brans_errors',
    )
    yanlis_sayisi = models.PositiveSmallIntegerField(default=0, verbose_name='Yanlış Sayısı')

    class Meta:
        verbose_name = 'Branş Konu Hatası'
        verbose_name_plural = 'Branş Konu Hataları'
        unique_together = [('brans_deneme', 'topic')]
        indexes = [models.Index(fields=['brans_deneme', 'topic'])]

    def __str__(self):
        return f'{self.topic.name}: {self.yanlis_sayisi}Y'

import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, full_name, role, password=None):
        if not email:
            raise ValueError('Email zorunludur')
        user = self.model(email=self.normalize_email(email), full_name=full_name, role=role)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, full_name, role='coach', password=None):
        user = self.create_user(email, full_name, role, password)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [('student', 'Öğrenci'), ('coach', 'Koç')]

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    coach = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='coached_students',
        limit_choices_to={'role': 'coach'},
    )
    THEME_CHOICES = [('auto', 'Otomatik'), ('light', 'Açık'), ('dark', 'Koyu')]

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    denemeler_v2 = models.BooleanField(default=False)
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='auto')
    grade = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    # ── Streak tracking ───────────────────────────────────────────────────────
    current_streak     = models.PositiveIntegerField(default=0)
    longest_streak     = models.PositiveIntegerField(default=0)
    last_activity_date = models.DateField(null=True, blank=True)
    tyt_target_date    = models.DateField(null=True, blank=True)
    ayt_target_date    = models.DateField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = UserManager()

    class Meta:
        verbose_name = 'Kullanıcı'
        verbose_name_plural = 'Kullanıcılar'

    def __str__(self):
        return f'{self.full_name} ({self.get_role_display()})'

    @property
    def is_student(self):
        return self.role == 'student'

    @property
    def is_coach(self):
        return self.role == 'coach'


class CoachStudent(models.Model):
    """Explicit coach-student relationship for access control and auditing (DAS-411)."""
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='coach_student_links',
        limit_choices_to={'role': 'coach'},
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_coach_links',
        limit_choices_to={'role': 'student'},
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('coach', 'student')
        verbose_name = 'Koç-Öğrenci İlişkisi'
        verbose_name_plural = 'Koç-Öğrenci İlişkileri'

    def __str__(self):
        return f'{self.coach.full_name} → {self.student.full_name}'


class CoachAuditLog(models.Model):
    """Tracks coach access to student data for privacy accountability (DAS-420)."""
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='audit_actions',
        limit_choices_to={'role': 'coach'},
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='coach_accesses',
        limit_choices_to={'role': 'student'},
    )
    action = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Koç Erişim Kaydı'
        verbose_name_plural = 'Koç Erişim Kayıtları'
        ordering = ['-timestamp']

    def __str__(self):
        student_name = self.student.full_name if self.student else '(silindi)'
        return f'{self.coach.full_name} → {student_name}: {self.action}'


class StudentAchievement(models.Model):
    STREAK_3      = 'streak_3'
    STREAK_7      = 'streak_7'
    STREAK_14     = 'streak_14'
    STREAK_30     = 'streak_30'
    STREAK_60     = 'streak_60'
    STREAK_100    = 'streak_100'
    EXAM_1        = 'exam_1'
    EXAM_10       = 'exam_10'
    EXAM_25       = 'exam_25'
    EXAM_50       = 'exam_50'
    TASK_10       = 'task_10'
    TASK_50       = 'task_50'
    COMEBACK      = 'comeback'
    PERFECT_WEEK  = 'perfect_week'

    BADGE_CHOICES = [
        (STREAK_3,     '3 Günlük Seri'),
        (STREAK_7,     '7 Günlük Seri'),
        (STREAK_14,    '14 Günlük Seri'),
        (STREAK_30,    '30 Günlük Seri'),
        (STREAK_60,    '60 Günlük Seri'),
        (STREAK_100,   '100 Günlük Seri'),
        (EXAM_1,       'İlk Sınav'),
        (EXAM_10,      '10 Sınav'),
        (EXAM_25,      '25 Sınav'),
        (EXAM_50,      '50 Sınav'),
        (TASK_10,      '10 Görev'),
        (TASK_50,      '50 Görev'),
        (COMEBACK,     'Yeniden Başladı'),
        (PERFECT_WEEK, 'Mükemmel Hafta'),
    ]

    BADGE_META = {
        STREAK_3:     {'icon': '🔥', 'hint': '3 gün üst üste çalış'},
        STREAK_7:     {'icon': '🔥', 'hint': '7 gün üst üste çalış'},
        STREAK_14:    {'icon': '🔥', 'hint': '14 gün üst üste çalış'},
        STREAK_30:    {'icon': '⭐', 'hint': '30 gün üst üste çalış'},
        STREAK_60:    {'icon': '💎', 'hint': '60 gün üst üste çalış'},
        STREAK_100:   {'icon': '👑', 'hint': '100 gün üst üste çalış'},
        EXAM_1:       {'icon': '📝', 'hint': 'İlk sınavını gir'},
        EXAM_10:      {'icon': '📊', 'hint': '10 sınav gir'},
        EXAM_25:      {'icon': '🎯', 'hint': '25 sınav gir'},
        EXAM_50:      {'icon': '🏆', 'hint': '50 sınav gir'},
        TASK_10:      {'icon': '✅', 'hint': '10 görevi tamamla'},
        TASK_50:      {'icon': '🌟', 'hint': '50 görevi tamamla'},
        COMEBACK:     {'icon': '💪', 'hint': 'Seriyi kaybedip yeniden başla'},
        PERFECT_WEEK: {'icon': '🗓️', 'hint': '7 gün hiç atlamadan çalış'},
    }

    student    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name='achievements', limit_choices_to={'role': 'student'})
    badge_key  = models.CharField(max_length=20, choices=BADGE_CHOICES, db_index=True)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('student', 'badge_key')]
        ordering = ['-awarded_at']
        verbose_name = 'Başarı Rozeti'
        verbose_name_plural = 'Başarı Rozetleri'

    def __str__(self):
        return f'{self.student.full_name} — {self.get_badge_key_display()}'


class CoachAlert(models.Model):
    CRITICAL  = 'critical'
    WARNING   = 'warning'
    POSITIVE  = 'positive'
    SEVERITY_CHOICES = [(CRITICAL,'Kritik'),(WARNING,'Uyarı'),(POSITIVE,'Olumlu')]

    EXAM_STAGNATION = 'exam_stagnation'
    NET_DECLINE     = 'net_decline'
    NET_MOMENTUM    = 'net_momentum'
    TASK_NEGLECT    = 'task_neglect'
    RADAR_OVERLOAD  = 'radar_overload'
    TYPE_CHOICES = [
        (EXAM_STAGNATION, 'Sınav Durağanlığı'),
        (NET_DECLINE,     'Net Düşüşü'),
        (NET_MOMENTUM,    'Net Artışı'),
        (TASK_NEGLECT,    'Görev İhmali'),
        (RADAR_OVERLOAD,  'Radar Birikimi'),
    ]

    coach       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='inbox_alerts', limit_choices_to={'role':'coach'})
    student     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='received_alerts', limit_choices_to={'role':'student'})
    alert_type  = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)
    severity    = models.CharField(max_length=10, choices=SEVERITY_CHOICES, db_index=True)
    title       = models.CharField(max_length=200)
    detail      = models.CharField(max_length=500, blank=True)
    metadata    = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    expires_at  = models.DateField(null=True, blank=True)
    is_read     = models.BooleanField(default=False, db_index=True)
    is_dismissed = models.BooleanField(default=False, db_index=True)

    class Meta:
        unique_together = [('coach', 'student', 'fingerprint')]
        ordering = ['-created_at']
        indexes = [models.Index(fields=['coach', 'is_dismissed', 'is_read'])]
        verbose_name = 'Koç Uyarısı'
        verbose_name_plural = 'Koç Uyarıları'

    def __str__(self):
        return f'[{self.severity}] {self.coach.full_name} → {self.student.full_name}: {self.title}'


class StudentInvite(models.Model):
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_invites',
        limit_choices_to={'role': 'coach'},
    )
    email     = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    token     = models.CharField(max_length=64, unique=True)
    is_used   = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Öğrenci Daveti'
        verbose_name_plural = 'Öğrenci Davetleri'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} ← {self.coach.full_name}'

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(32)  # 256-bit entropy, URL-safe

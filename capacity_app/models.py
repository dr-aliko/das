import uuid

from django.conf import settings
from django.db import models


class CapacitySettings(models.Model):
    """Singleton: slot price + editable how-it-works explanation card for coaches."""
    per_slot_price_kurus = models.PositiveIntegerField(
        default=0,
        help_text='Slot başına fiyat (kuruş). 100 = 1 ₺.',
    )
    explanation_title = models.CharField(
        max_length=200,
        default='Kontenjan nasıl çalışır?',
        blank=True,
    )
    explanation_body = models.TextField(
        default='',
        blank=True,
        help_text=(
            'Her satır bir madde. '
            '"Başlık: açıklama" → başlık kalın gösterilir. '
            '"! not" satırı vurgulu kutu olur. En fazla 8 madde, 1500 karakter.'
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    class Meta:
        verbose_name = 'Kontenjan Ayarları'
        verbose_name_plural = 'Kontenjan Ayarları'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'per_slot_price_kurus': 0})
        return obj

    @property
    def per_slot_price_tl(self):
        return self.per_slot_price_kurus // 100


class CoachCapacityOrder(models.Model):
    STATUS_PENDING           = 'pending'
    STATUS_AWAITING_TRANSFER = 'awaiting_transfer'
    STATUS_PAID              = 'paid'
    STATUS_CANCELLED         = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING,           'Bekliyor'),
        (STATUS_AWAITING_TRANSFER, 'Havale Bekleniyor'),
        (STATUS_PAID,              'Ödendi'),
        (STATUS_CANCELLED,         'İptal Edildi'),
    ]

    token            = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    coach            = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='capacity_orders',
        limit_choices_to={'role': 'coach'},
    )
    slots            = models.PositiveIntegerField()
    amount_kurus     = models.PositiveIntegerField(help_text='Sipariş anındaki tutar (kuruş)')
    per_slot_kurus   = models.PositiveIntegerField(help_text='Sipariş anındaki slot fiyatı (kuruş)')
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                        default=STATUS_PENDING, db_index=True)
    ref_code         = models.CharField(max_length=20, unique=True, null=True, blank=True)
    payment_claimed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    sender_name      = models.CharField(max_length=80, blank=True, default='')
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Kontenjan Siparişi'
        verbose_name_plural = 'Kontenjan Siparişleri'
        ordering            = ['-created_at']

    def __str__(self):
        return f'#{self.pk} {self.coach.full_name} — {self.slots} slot [{self.get_status_display()}]'

    @property
    def amount_tl_display(self):
        tl = self.amount_kurus // 100
        return f'{tl:,}'.replace(',', '.') + ' ₺'


class CoachCapacityGrant(models.Model):
    """Active or past capacity grant for a coach (paid order or staff comp)."""
    coach        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='capacity_grants',
        limit_choices_to={'role': 'coach'},
    )
    order        = models.OneToOneField(
        CoachCapacityOrder,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='grant',
    )
    slots        = models.PositiveIntegerField()
    period_start = models.DateField()
    period_end   = models.DateField()
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Kontenjan Hakkı'
        verbose_name_plural = 'Kontenjan Hakları'
        ordering            = ['-period_start']

    def __str__(self):
        return f'{self.coach.full_name}: {self.slots} slot ({self.period_start} – {self.period_end})'

    @property
    def is_active(self):
        from datetime import date
        today = date.today()
        return self.period_start <= today <= self.period_end


class GrantAdjustmentLog(models.Model):
    """Audit trail for every staff-initiated grant reduction or early termination."""
    ACTION_REDUCE = 'reduce'
    ACTION_END    = 'end'
    ACTION_CHOICES = [
        (ACTION_REDUCE, 'Azalt'),
        (ACTION_END,    'Sonlandır'),
    ]

    grant          = models.ForeignKey(
        CoachCapacityGrant,
        on_delete=models.PROTECT,
        related_name='adjustments',
    )
    adjusted_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='+',
    )
    adjusted_at    = models.DateTimeField(auto_now_add=True)
    action         = models.CharField(max_length=10, choices=ACTION_CHOICES)
    reason         = models.TextField()
    old_slots      = models.PositiveIntegerField()
    new_slots      = models.PositiveIntegerField()
    old_period_end = models.DateField()
    new_period_end = models.DateField()

    class Meta:
        ordering            = ['-adjusted_at']
        verbose_name        = 'Kontenjan Düzeltme Kaydı'
        verbose_name_plural = 'Kontenjan Düzeltme Kayıtları'

    def __str__(self):
        return (
            f'Grant#{self.grant_id} {self.get_action_display()} '
            f'by {self.adjusted_by_id} at {self.adjusted_at}'
        )


class CoachCreditLedger(models.Model):
    """Credit ledger for COACH_PER_STUDENT_PERIODS: one credit = one coach-own-student slot."""
    REASON_PURCHASE_APPROVED      = 'purchase_approved'
    REASON_MANUAL_GRANT           = 'manual_grant'
    REASON_CONVERTED_FROM_GRANT   = 'converted_from_grant'
    REASON_CONSUMED_INVITE        = 'consumed_invite'
    REASON_STAFF_ADJUSTMENT       = 'staff_adjustment'
    REASON_TRANSITION_FIRST_PERIOD = 'transition_first_period'
    REASON_CHOICES = [
        (REASON_PURCHASE_APPROVED,       'Satın alma onaylandı'),
        (REASON_MANUAL_GRANT,            'Manuel kredi verildi'),
        (REASON_CONVERTED_FROM_GRANT,    'Kontenjan hakkından dönüştürüldü'),
        (REASON_CONSUMED_INVITE,         'Davet tüketti'),
        (REASON_STAFF_ADJUSTMENT,        'Personel düzenlemesi'),
        (REASON_TRANSITION_FIRST_PERIOD, 'İlk dönem geçiş kredisi'),
    ]

    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='credit_ledger_entries',
        limit_choices_to={'role': 'coach'},
    )
    delta = models.IntegerField(help_text='Pozitif: kredi eklendi. Negatif: kredi tükendi.')
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    order = models.ForeignKey(
        CoachCapacityOrder,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='credit_entries',
    )
    coach_student = models.ForeignKey(
        'users_app.CoachStudent',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='credit_entries',
    )
    invite = models.ForeignKey(
        'users_app.StudentInvite',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='credit_entries',
    )
    notes = models.CharField(max_length=500, blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Kredi Kaydı'
        verbose_name_plural = 'Kredi Kayıtları'
        ordering            = ['-created_at']
        constraints = [
            # One invite may consume at most one credit.
            models.UniqueConstraint(
                fields=['invite'],
                condition=models.Q(reason='consumed_invite'),
                name='unique_invite_per_consumed_credit',
            ),
        ]

    def __str__(self):
        return f'{self.coach.full_name}: {self.delta:+d} [{self.get_reason_display()}]'


class CoachStudentRenewalOrder(models.Model):
    """Per-student renewal payment order (used when COACH_PER_STUDENT_PERIODS is True)."""
    STATUS_AWAITING_TRANSFER = 'awaiting_transfer'
    STATUS_PAID              = 'paid'
    STATUS_CANCELLED         = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_AWAITING_TRANSFER, 'Havale Bekleniyor'),
        (STATUS_PAID,              'Ödendi'),
        (STATUS_CANCELLED,         'İptal Edildi'),
    ]

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    coach_student = models.ForeignKey(
        'users_app.CoachStudent',
        on_delete=models.PROTECT,
        related_name='renewal_orders',
    )
    amount_kurus      = models.PositiveIntegerField(help_text='Sipariş tutarı (kuruş)')
    per_student_kurus = models.PositiveIntegerField(
        help_text='Sipariş anındaki öğrenci başı fiyat (kuruş)'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_AWAITING_TRANSFER, db_index=True,
    )
    ref_code           = models.CharField(max_length=20, unique=True)
    payment_claimed_at = models.DateTimeField(null=True, blank=True)
    sender_name        = models.CharField(max_length=80, blank=True, default='')
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Öğrenci Yenileme Siparişi'
        verbose_name_plural = 'Öğrenci Yenileme Siparişleri'
        ordering            = ['-created_at']
        constraints = [
            # At most one open (awaiting_transfer) renewal per coach-student link.
            models.UniqueConstraint(
                fields=['coach_student'],
                condition=models.Q(status='awaiting_transfer'),
                name='unique_open_renewal_per_coach_student',
            ),
        ]

    def __str__(self):
        return f'#{self.pk} {self.coach_student} [{self.get_status_display()}]'

    @property
    def amount_tl_display(self):
        tl = self.amount_kurus // 100
        return f'{tl:,}'.replace(',', '.') + ' ₺'

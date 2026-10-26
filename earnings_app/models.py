from django.conf import settings
from django.db import models


class ManualPaymentRecord(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='manual_payment_records',
        limit_choices_to={'role': 'student'},
    )
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='manual_payment_coach_records',
        limit_choices_to={'role': 'coach'},
    )
    amount_kurus = models.PositiveIntegerField(help_text='Tam ödeme tutarı (kuruş)')
    coach_pool_kurus = models.PositiveIntegerField(help_text='Koça gidecek havuz (kuruş)')
    date = models.DateField(help_text='Kapsam başlangıç tarihi')
    days = models.PositiveIntegerField(help_text='Kapsam süresi (gün)')
    note = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_manual_payment_records',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Manuel Ödeme Kaydı'
        verbose_name_plural = 'Manuel Ödeme Kayıtları'
        ordering = ['-created_at']

    def __str__(self):
        return f'Manuel #{self.pk}: {self.student} — {self.date} ({self.days} gün)'


class EarningRow(models.Model):
    STATUS_HELD     = 'held'
    STATUS_RELEASED = 'released'
    STATUS_APPROVED = 'approved'
    STATUS_PAID     = 'paid'
    STATUS_VOID     = 'void'
    STATUS_CHOICES = [
        (STATUS_HELD,     'Beklemede'),
        (STATUS_RELEASED, 'Serbest'),
        (STATUS_APPROVED, 'Onaylandı'),
        (STATUS_PAID,     'Ödendi'),
        (STATUS_VOID,     'İptal'),
    ]

    KIND_EARNING    = 'earning'
    KIND_ADJUSTMENT = 'adjustment'
    KIND_CHOICES = [
        (KIND_EARNING,    'Kazanç'),
        (KIND_ADJUSTMENT, 'Düzeltme'),
    ]

    order = models.ForeignKey(
        'purchase_app.Order',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='earning_rows',
    )
    manual_record = models.ForeignKey(
        ManualPaymentRecord,
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='earning_rows',
    )
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='earning_rows',
        limit_choices_to={'role': 'coach'},
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='student_earning_rows',
        limit_choices_to={'role': 'student'},
    )

    coverage_start = models.DateField()
    coverage_end   = models.DateField(help_text='Kapsam bitiş (dahil değil)')
    period_days    = models.PositiveIntegerField()
    coach_days     = models.PositiveIntegerField()
    pool_kurus     = models.PositiveIntegerField(help_text='Toplam koç havuzu snapshotu (kuruş)')
    amount_kurus   = models.IntegerField(help_text='İşaretli kuruş; negatif = düzeltme')

    kind       = models.CharField(max_length=12, choices=KIND_CHOICES, default=KIND_EARNING)
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_HELD, db_index=True)
    gap_fallback = models.BooleanField(default=False,
                                       help_text='Aralık günlüğü boşluğu; mevcut koça atandı')

    split_from_reassign = models.BooleanField(
        default=False,
        help_text='Koç değişikliği sırasında orantısal bölünme ile oluşturuldu',
    )

    payout_ref  = models.CharField(max_length=255, blank=True, default='')
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_earnings',
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='paid_out_earnings',
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='voided_earnings',
    )
    void_reason = models.TextField(blank=True, default='')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Kazanç Satırı'
        verbose_name_plural = 'Kazanç Satırları'
        indexes = [
            models.Index(fields=['coach', 'status']),
            models.Index(fields=['order', 'status']),
            models.Index(fields=['coverage_end', 'status']),
        ]
        ordering = ['-coverage_start', '-created_at']

    def __str__(self):
        return (
            f'EarningRow #{self.pk} [{self.get_status_display()}] '
            f'{self.coverage_start}–{self.coverage_end}'
        )


class EarningConfig(models.Model):
    """Singleton admin-editable percentages shown on the panel summary."""
    provider_commission_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Ödeme sağlayıcı komisyonu (% BRÜT gösterim için bilgi amaçlı)',
    )
    tax_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Vergi oranı (% BRÜT gösterim için bilgi amaçlı)',
    )

    class Meta:
        verbose_name = 'Kazanç Yapılandırması'
        verbose_name_plural = 'Kazanç Yapılandırması'

    def __str__(self):
        return f'Komisyon %{self.provider_commission_pct} / Vergi %{self.tax_pct}'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

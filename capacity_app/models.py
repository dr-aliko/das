import uuid

from django.conf import settings
from django.db import models


class CapacitySettings(models.Model):
    """Singleton price table for coach capacity slots (whole TL input stored in kuruş)."""
    per_slot_price_kurus = models.PositiveIntegerField(
        default=0,
        help_text='Slot başına fiyat (kuruş). 100 = 1 ₺.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Kontenjan Fiyat Ayarı'
        verbose_name_plural = 'Kontenjan Fiyat Ayarları'

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

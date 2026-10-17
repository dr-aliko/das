import uuid

from django.conf import settings
from django.db import models


class Plan(models.Model):
    KIND_ONE_TIME     = 'one_time'
    KIND_SUBSCRIPTION = 'subscription'
    KIND_CHOICES = [
        (KIND_ONE_TIME,     'Tek Seferlik'),
        (KIND_SUBSCRIPTION, 'Abonelik'),
    ]

    name          = models.CharField(max_length=255)
    kind          = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_ONE_TIME)
    price_kurus   = models.PositiveIntegerField(help_text='Kuruş cinsinden (örn. 319900 = 3199,00 ₺)')
    duration_days = models.PositiveIntegerField()
    active        = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name         = 'Plan'
        verbose_name_plural  = 'Planlar'
        ordering             = ['kind', 'price_kurus']

    def __str__(self):
        return f'{self.name} ({self.price_kurus / 100:.2f} ₺, {self.duration_days} gün)'

    @property
    def price_tl(self):
        return self.price_kurus / 100

    @property
    def price_display(self):
        tl = self.price_kurus // 100
        kurus = self.price_kurus % 100
        tl_str = f'{tl:,}'.replace(',', '.')
        if kurus:
            return f'{tl_str},{kurus:02d} ₺'
        return f'{tl_str} ₺'


class Order(models.Model):
    STATUS_PENDING      = 'pending'
    STATUS_PAID         = 'paid'
    STATUS_FAILED       = 'failed'
    STATUS_CANCELLED    = 'cancelled'
    STATUS_REFUNDED     = 'refunded'
    STATUS_NEEDS_REVIEW = 'needs_review'
    STATUS_CHOICES = [
        (STATUS_PENDING,      'Bekliyor'),
        (STATUS_PAID,         'Ödendi'),
        (STATUS_FAILED,       'Başarısız'),
        (STATUS_CANCELLED,    'İptal Edildi'),
        (STATUS_REFUNDED,     'İade Edildi'),
        (STATUS_NEEDS_REVIEW, 'İnceleme Gerekiyor'),
    ]

    token        = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    student      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='purchase_orders',
        limit_choices_to={'role': 'student'},
    )
    email        = models.EmailField()
    coach        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='received_orders',
        limit_choices_to={'role': 'coach'},
    )
    plan         = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='orders')
    amount_kurus = models.PositiveIntegerField(help_text='Sipariş anındaki fiyat snapshotu (kuruş)')
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    provider     = models.CharField(max_length=64)
    provider_ref = models.CharField(max_length=255, unique=True, null=True, blank=True)
    full_name    = models.CharField(max_length=255)
    phone        = models.CharField(max_length=32, blank=True, default='')
    guardian_name  = models.CharField(max_length=255, blank=True, default='')
    guardian_phone = models.CharField(max_length=32,  blank=True, default='')
    sinif          = models.CharField(max_length=5,   blank=True, default='')
    alan           = models.CharField(max_length=5,   blank=True, default='')
    seen_by_coach  = models.BooleanField(default=False)
    notes        = models.TextField(blank=True, default='')
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Sipariş'
        verbose_name_plural = 'Siparişler'
        ordering            = ['-created_at']

    def __str__(self):
        return f'#{self.pk} [{self.get_status_display()}] {self.email}'

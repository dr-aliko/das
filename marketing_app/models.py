from django.conf import settings
from django.db import models
from django.utils.text import slugify


ACCENT_CHOICES = [
    ('indigo', 'İndigo'),
    ('violet', 'Mor'),
    ('emerald', 'Zümrüt'),
    ('amber', 'Kehribar'),
    ('ruby', 'Kırmızı'),
]


class SiteSettings(models.Model):
    """Singleton — one row (pk=1) holds all admin-editable public site copy."""

    # Hero
    hero_eyebrow = models.CharField(max_length=120, default='YKS 2027 · Akıllı çalışma platformu')
    hero_title_line1 = models.CharField(max_length=120, default='YKS hazırlığını')
    hero_title_line2 = models.CharField(max_length=120, default='plansız bırakma.')
    hero_subtitle = models.TextField(
        default=(
            'Vagus; deneme analizlerini, konu eksiklerini, haftalık görevlerini ve '
            'TYT/AYT yol haritanı tek panelde takip etmeni sağlar. '
            'Ne çalışacağını, ne zaman çalışacağını ve nasıl geliştiğini net gör.'
        )
    )
    hero_cta_primary_label = models.CharField(max_length=60, default='Hemen Başla')
    hero_cta_primary_url = models.CharField(max_length=200, default='/auth/register/')
    hero_cta_secondary_label = models.CharField(max_length=60, default='Demo İncele')
    hero_cta_secondary_url = models.CharField(max_length=200, default='/ozellikler/')

    # Final CTA section
    final_cta_title = models.CharField(max_length=160, default='YKS sürecini bugün düzene koy.')
    final_cta_subtitle = models.CharField(
        max_length=240, default='Kredi kartı gerekmez. Kayıt 60 saniye.'
    )

    # Navbar CTA
    nav_cta_label = models.CharField(max_length=60, default='Hemen Başla')
    nav_cta_url = models.CharField(max_length=200, default='/auth/register/')

    # Footer
    footer_tagline = models.TextField(
        default=(
            'YKS hazırlığında ne çalışacağını, ne zaman çalışacağını ve nasıl '
            'geliştiğini net gösteren akıllı çalışma platformu.'
        )
    )
    footer_copyright = models.CharField(max_length=100, default='© 2026 Vagus. Tüm hakları saklıdır.')
    footer_location = models.CharField(max_length=60, default='Ankara · Türkiye')

    # Contact info
    contact_email = models.EmailField(default='hello@vagus.app')
    contact_corporate_email = models.EmailField(default='kurumsal@vagus.app')
    contact_whatsapp = models.CharField(max_length=30, default='+90 532 444 55 66')

    class Meta:
        verbose_name = 'Site Ayarları'
        verbose_name_plural = 'Site Ayarları'

    def __str__(self):
        return 'Site Ayarları'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # prevent deletion

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class FeatureItem(models.Model):
    slug = models.SlugField(unique=True)
    order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=100)
    subtitle = models.CharField(max_length=240, help_text='Kısa açıklama (ana sayfa kartı)')
    body = models.TextField(blank=True, help_text='Uzun açıklama (özellikler sayfası)')
    icon_svg = models.TextField(blank=True, help_text='Inline SVG markup (viewBox 0 0 20 20 ölçüsünde)')
    accent = models.CharField(max_length=10, choices=ACCENT_CHOICES[:3], default='indigo')
    is_published = models.BooleanField(default=True)
    show_on_home = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Özellik Kartı'
        verbose_name_plural = 'Özellik Kartları'

    def __str__(self):
        return self.title


class PricingPlan(models.Model):
    slug = models.SlugField(unique=True)
    order = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=80)
    badge_label = models.CharField(max_length=60, blank=True, help_text='Örn: ★ En Çok Tercih Edilen')
    is_featured = models.BooleanField(default=False, help_text='Öne çıkan plan (primary buton stilini alır)')
    price_monthly_try = models.PositiveIntegerField(help_text='Aylık TL fiyatı')
    subtitle = models.CharField(max_length=120, blank=True)
    summary = models.CharField(max_length=160, blank=True, help_text='Örn: Toplam ₺594 — 1 ay hediye · %33 indirim')
    cta_label = models.CharField(max_length=60, default='Hemen Başla')
    cta_url = models.CharField(max_length=200, default='/auth/register/')
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Fiyat Planı'
        verbose_name_plural = 'Fiyat Planları'

    def __str__(self):
        return self.name


class PricingFeature(models.Model):
    plan = models.ForeignKey(PricingPlan, on_delete=models.CASCADE, related_name='features')
    order = models.PositiveIntegerField(default=0)
    text = models.CharField(max_length=200)

    class Meta:
        ordering = ['order']
        verbose_name = 'Plan Özelliği'
        verbose_name_plural = 'Plan Özellikleri'

    def __str__(self):
        return f'{self.plan.name} – {self.text[:50]}'


class FAQItem(models.Model):
    CATEGORY_CHOICES = [('student', 'Öğrenciler için'), ('parent', 'Veliler için')]

    order = models.PositiveIntegerField(default=0)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default='student')
    question = models.CharField(max_length=240)
    answer = models.TextField()
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'order']
        verbose_name = 'SSS'
        verbose_name_plural = 'SSS (Sıkça Sorulan Sorular)'

    def __str__(self):
        return self.question[:80]


class Testimonial(models.Model):
    order = models.PositiveIntegerField(default=0)
    student_name = models.CharField(max_length=60)
    initials = models.CharField(max_length=2)
    accent = models.CharField(
        max_length=20,
        choices=[('violet-indigo', 'Mor-İndigo'), ('emerald', 'Zümrüt'), ('amber', 'Kehribar')],
        default='violet-indigo',
    )
    quote = models.TextField()
    student_info = models.CharField(max_length=120, blank=True, help_text='Örn: 12. Sınıf · Sayısal · İstanbul')
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Öğrenci Görüşü'
        verbose_name_plural = 'Öğrenci Görüşleri'

    def __str__(self):
        return f'{self.student_name} – {self.quote[:60]}'

    def avatar_gradient(self):
        gradients = {
            'violet-indigo': 'linear-gradient(135deg,var(--violet),var(--indigo))',
            'emerald': 'linear-gradient(135deg,#10b981,#059669)',
            'amber': 'linear-gradient(135deg,#f59e0b,#d97706)',
        }
        return gradients.get(self.accent, gradients['violet-indigo'])


class CoachProfile(models.Model):
    """Public-facing coach profile. Separate from the operational User model."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='public_profile',
        limit_choices_to={'role': 'coach'},
    )
    slug = models.SlugField(unique=True, blank=True)
    display_name = models.CharField(
        max_length=100, blank=True, help_text='Boş bırakılırsa kullanıcı adı kullanılır'
    )
    title = models.CharField(max_length=120, blank=True, help_text='Örn: Matematik Koçu')
    specialty = models.CharField(max_length=200, blank=True, help_text='Örn: Sayısal · AYT Matematik')
    bio_short = models.CharField(max_length=200, blank=True, help_text='Liste kartında gösterilen kısa bio')
    bio_long = models.TextField(blank=True, help_text='Profil detay sayfasında gösterilen uzun bio')
    photo = models.ImageField(upload_to='coaches/', blank=True, null=True)
    accent = models.CharField(
        max_length=10,
        choices=[
            ('indigo', 'İndigo'),
            ('violet', 'Mor'),
            ('emerald', 'Zümrüt'),
            ('amber', 'Kehribar'),
        ],
        default='indigo',
        help_text='Fotoğraf yoksa kullanılacak avatar rengi',
    )
    years_experience = models.PositiveIntegerField(null=True, blank=True, help_text='Yıl olarak deneyim')
    student_count = models.PositiveIntegerField(null=True, blank=True, help_text='Örn: 120 → "120+ öğrenci"')
    success_metric = models.CharField(
        max_length=120, blank=True, help_text='Örn: Ortalama +12 net artışı'
    )
    is_public = models.BooleanField(
        default=False,
        help_text='İşaretlenirse koç /koclar/ sayfasında görünür',
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'pk']
        verbose_name = 'Koç Profili (Genel Site)'
        verbose_name_plural = 'Koç Profilleri (Genel Site)'

    def __str__(self):
        return self.get_display_name()

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.display_name or self.user.full_name)
            slug = base
            n = 1
            while CoachProfile.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_display_name(self):
        return self.display_name or self.user.full_name

    def avatar_gradient(self):
        gradients = {
            'indigo': 'linear-gradient(135deg,var(--indigo),var(--indigo-deep))',
            'violet': 'linear-gradient(135deg,var(--violet),var(--violet-deep))',
            'emerald': 'linear-gradient(135deg,#10b981,#059669)',
            'amber': 'linear-gradient(135deg,#f59e0b,#d97706)',
        }
        return gradients.get(self.accent, gradients['indigo'])

    def avatar_initials(self):
        name = self.get_display_name()
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return name[:2].upper()


class CoachRequest(models.Model):
    STATUS_NEW = 'new'
    STATUS_CONTACTED = 'contacted'
    STATUS_CONVERTED = 'converted'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_NEW, 'Yeni'),
        (STATUS_CONTACTED, 'İletişime Geçildi'),
        (STATUS_CONVERTED, 'Dönüştürüldü'),
        (STATUS_REJECTED, 'Reddedildi'),
    ]

    TRACK_CHOICES = [
        ('sayisal', 'Sayısal'),
        ('ea', 'Eşit Ağırlık'),
        ('sozel', 'Sözel'),
        ('dil', 'Dil'),
        ('unknown', 'Henüz belli değil'),
    ]

    GRADE_CHOICES = [
        ('9', '9. Sınıf'),
        ('10', '10. Sınıf'),
        ('11', '11. Sınıf'),
        ('12', '12. Sınıf'),
        ('mezun', 'Mezun'),
    ]

    coach_profile = models.ForeignKey(
        CoachProfile,
        on_delete=models.SET_NULL,
        null=True,
        related_name='requests',
        verbose_name='Koç',
    )
    full_name = models.CharField(max_length=120, verbose_name='Ad Soyad')
    email = models.EmailField(verbose_name='E-posta')
    phone = models.CharField(max_length=30, verbose_name='Telefon')
    grade_level = models.CharField(max_length=10, choices=GRADE_CHOICES, verbose_name='Sınıf')
    target_exam_year = models.PositiveSmallIntegerField(verbose_name='Hedef Sınav Yılı')
    track = models.CharField(max_length=10, choices=TRACK_CHOICES, verbose_name='Alan')
    note = models.TextField(blank=True, verbose_name='Kısa Not')
    parent_name = models.CharField(max_length=120, blank=True, verbose_name='Veli Adı')
    parent_phone = models.CharField(max_length=30, blank=True, verbose_name='Veli Telefonu')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_NEW, verbose_name='Durum')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Koç Talebi'
        verbose_name_plural = 'Koç Talepleri'

    def __str__(self):
        coach_name = self.coach_profile.get_display_name() if self.coach_profile else '—'
        return f'{self.full_name} → {coach_name}'

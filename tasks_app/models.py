from django.conf import settings
from django.db import models


class AktiviteTipi(models.TextChoices):
    KONU_ANLATIMI = "konu_anlatimi", "Konu Anlatımı"
    SORU_COZUMU   = "soru_cozumu",   "Soru Çözümü"
    TEKRAR        = "tekrar",        "Tekrar"


class GorevGrubu(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="gorev_gruplari",
        limit_choices_to={'role': 'student'},
    )
    tarih = models.DateField()
    aktivite_tipi = models.CharField(
        max_length=32, choices=AktiviteTipi.choices, null=True, blank=True
    )
    ozel_sure_dk = models.IntegerField(null=True, blank=True)
    ders_title   = models.CharField(max_length=255, null=True, blank=True)
    sira_no      = models.IntegerField(default=0)
    # {sinav_tipi, ders_id, liste_id, videos:[{id,title,duration}]} for konu_anlatimi only
    meta         = models.JSONField(null=True, blank=True)
    is_completed  = models.BooleanField(default=False)
    completed_at  = models.DateTimeField(null=True, blank=True)
    # Student's self-rating on tekrar tasks: easy / medium / hard
    tekrar_quality = models.CharField(max_length=16, null=True, blank=True)
    # Coach can grant the student edit/reorder rights on this specific task
    student_can_edit = models.BooleanField(default=False)
    # Versioning: coach tasks are masters; student edits create non-master copies
    is_master = models.BooleanField(default=True)
    # Student can soft-hide a master task (not delete); reset clears this flag
    is_hidden_by_student = models.BooleanField(default=False)
    parent    = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='student_copies',
    )
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Görev Grubu'
        verbose_name_plural = 'Görev Grupları'
        ordering = ["tarih", "sira_no"]
        indexes = [models.Index(fields=["student", "tarih"])]

    def __str__(self):
        return f"{self.student} / {self.tarih} / {self.ders_title}"


class GrupDetay(models.Model):
    grup = models.ForeignKey(
        GorevGrubu, on_delete=models.CASCADE, related_name="detaylar"
    )
    aciklama     = models.TextField(null=True, blank=True)
    sure_bilgisi = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        verbose_name = 'Grup Detayı'
        verbose_name_plural = 'Grup Detayları'

    def __str__(self):
        return self.aciklama or ""


class YouTubePlaylist(models.Model):
    playlist_id   = models.CharField(max_length=64, unique=True)
    title         = models.CharField(max_length=255)
    channel_title = models.CharField(max_length=255, blank=True)
    subject       = models.ForeignKey(
        'exams_app.Subject',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='youtube_playlists',
    )
    exam_type     = models.CharField(
        max_length=3, choices=[('TYT', 'TYT'), ('AYT', 'AYT')], default='TYT',
    )
    imported_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='imported_playlists',
    )
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'YouTube Playlist'
        verbose_name_plural = 'YouTube Playlistler'
        ordering = ['exam_type', 'title']

    def __str__(self):
        return self.title


class YouTubeVideo(models.Model):
    playlist     = models.ForeignKey(
        YouTubePlaylist, on_delete=models.CASCADE, related_name='videos',
    )
    video_id     = models.CharField(max_length=32)
    title        = models.CharField(max_length=300)
    duration_min = models.PositiveIntegerField(default=0)
    position     = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'YouTube Video'
        verbose_name_plural = 'YouTube Videolar'
        unique_together = [('playlist', 'video_id')]
        ordering = ['position']

    def __str__(self):
        return self.title


class KaynakKitap(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kaynak_kitaplar",
        limit_choices_to={'role': 'student'},
    )
    kitap_adi  = models.CharField(max_length=255)
    ders       = models.CharField(max_length=64)
    sinav_tipi = models.CharField(max_length=32)

    class Meta:
        verbose_name = 'Kaynak Kitap'
        verbose_name_plural = 'Kaynak Kitaplar'
        constraints = [
            models.UniqueConstraint(
                fields=["student", "kitap_adi", "ders", "sinav_tipi"],
                name="uniq_kaynak_per_student",
            ),
        ]
        ordering = ["kitap_adi"]

    def __str__(self):
        return f"{self.kitap_adi} ({self.sinav_tipi} - {self.ders})"

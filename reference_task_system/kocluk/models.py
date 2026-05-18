from django.conf import settings
from django.db import models


class AktiviteTipi(models.TextChoices):
    KONU_ANLATIMI = "konu_anlatimi", "Konu Anlatımı"
    SORU_COZUMU = "soru_cozumu", "Soru Çözümü"
    TEKRAR = "tekrar", "Tekrar"


class Ogrenci(models.Model):
    koc = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ogrenciler",
    )
    ad_soyad = models.CharField(max_length=200)
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["koc", "ad_soyad"], name="uniq_koc_ad_soyad"),
        ]
        ordering = ["ad_soyad"]

    def __str__(self) -> str:
        return self.ad_soyad


class GorevGrubu(models.Model):
    ogrenci = models.ForeignKey(
        Ogrenci, on_delete=models.CASCADE, related_name="gorev_gruplari"
    )
    tarih = models.DateField()
    aktivite_tipi = models.CharField(
        max_length=32, choices=AktiviteTipi.choices, null=True, blank=True
    )
    ozel_sure_dk = models.IntegerField(null=True, blank=True)
    # Denormalized: "TYT - Matematik" for Soru Çözümü/Tekrar, or playlist title for Konu Anlatımı
    ders_title = models.CharField(max_length=255, null=True, blank=True)
    sira_no = models.IntegerField(default=0)
    # Stores {sinav_tipi, ders_id, liste_id} for konu_anlatimi tasks so edits can restore selections.
    meta = models.JSONField(null=True, blank=True)
    olusturulma_tarihi = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tarih", "sira_no"]
        indexes = [models.Index(fields=["ogrenci", "tarih"])]

    def __str__(self) -> str:
        return f"{self.ogrenci} / {self.tarih} / {self.ders_title}"


class GrupDetay(models.Model):
    grup = models.ForeignKey(
        GorevGrubu, on_delete=models.CASCADE, related_name="detaylar"
    )
    # Denormalized: "KaynakKitapAdi: açıklama" for Soru Çözümü/Tekrar, or video title for Konu Anlatımı
    aciklama = models.TextField(null=True, blank=True)
    sure_bilgisi = models.CharField(max_length=64, null=True, blank=True)

    def __str__(self) -> str:
        return self.aciklama or ""


class KaynakKitap(models.Model):
    ogrenci = models.ForeignKey(
        Ogrenci, on_delete=models.CASCADE, related_name="kaynak_kitaplar"
    )
    kitap_adi = models.CharField(max_length=255)
    ders = models.CharField(max_length=64)
    sinav_tipi = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ogrenci", "kitap_adi", "ders", "sinav_tipi"],
                name="uniq_kaynak_per_ogrenci",
            ),
        ]
        ordering = ["kitap_adi"]

    def __str__(self) -> str:
        return f"{self.kitap_adi} ({self.sinav_tipi} - {self.ders})"

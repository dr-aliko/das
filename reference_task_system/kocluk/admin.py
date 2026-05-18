from django.contrib import admin

from kocluk.models import GorevGrubu, GrupDetay, KaynakKitap, Ogrenci


class GrupDetayInline(admin.TabularInline):
    model = GrupDetay
    extra = 0


@admin.register(Ogrenci)
class OgrenciAdmin(admin.ModelAdmin):
    list_display = ["ad_soyad", "koc", "olusturulma_tarihi"]
    list_filter = ["koc"]
    search_fields = ["ad_soyad"]


@admin.register(GorevGrubu)
class GorevGrubuAdmin(admin.ModelAdmin):
    list_display = ["ogrenci", "tarih", "aktivite_tipi", "ders_title", "ozel_sure_dk", "sira_no"]
    list_filter = ["aktivite_tipi", "ogrenci__koc"]
    search_fields = ["ders_title", "ogrenci__ad_soyad"]
    inlines = [GrupDetayInline]


@admin.register(KaynakKitap)
class KaynakKitapAdmin(admin.ModelAdmin):
    list_display = ["kitap_adi", "ders", "sinav_tipi", "ogrenci"]
    list_filter = ["sinav_tipi", "ders"]

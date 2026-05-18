from django.contrib import admin

from tasks_app.models import GorevGrubu, GrupDetay, KaynakKitap


class GrupDetayInline(admin.TabularInline):
    model = GrupDetay
    extra = 0


@admin.register(GorevGrubu)
class GorevGrubuAdmin(admin.ModelAdmin):
    list_display = ["student", "tarih", "aktivite_tipi", "ders_title", "ozel_sure_dk", "sira_no"]
    list_filter = ["aktivite_tipi", "student__coach"]
    search_fields = ["ders_title", "student__full_name"]
    inlines = [GrupDetayInline]


@admin.register(KaynakKitap)
class KaynakKitapAdmin(admin.ModelAdmin):
    list_display = ["kitap_adi", "ders", "sinav_tipi", "student"]
    list_filter = ["sinav_tipi", "ders"]
    search_fields = ["kitap_adi", "student__full_name"]

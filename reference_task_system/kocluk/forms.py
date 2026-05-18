import json
from datetime import date

from django import forms

from kocluk.models import AktiviteTipi


class OgrenciForm(forms.Form):
    ad_soyad = forms.CharField(max_length=200, strip=True)

    def clean_ad_soyad(self):
        val = self.cleaned_data["ad_soyad"].strip()
        if not val:
            raise forms.ValidationError("İsim boş olamaz.")
        return val


class GorevForm(forms.Form):
    ogrenci_id = forms.IntegerField(required=False)
    tarih = forms.DateField()
    aktivite_tipi = forms.ChoiceField(choices=AktiviteTipi.choices)
    ders_title = forms.CharField(max_length=255, required=False)
    ozel_sure_dk = forms.IntegerField(required=False, min_value=0)
    detaylar = forms.CharField(required=False)  # JSON string from client

    def clean_detaylar(self):
        raw = self.cleaned_data.get("detaylar", "")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raise forms.ValidationError("Detaylar geçerli JSON değil.")
        if not isinstance(data, list):
            raise forms.ValidationError("Detaylar bir liste olmalı.")
        result = []
        for item in data:
            aciklama = (item.get("aciklama") or "").strip()
            if not aciklama:
                raise forms.ValidationError("Her detayın bir açıklaması olmalı.")
            result.append({"aciklama": aciklama, "sure_bilgisi": item.get("sure_bilgisi")})
        return result

    def clean(self):
        cleaned = super().clean()
        aktivite = cleaned.get("aktivite_tipi")
        detaylar = cleaned.get("detaylar", [])
        ders_title = (cleaned.get("ders_title") or "").strip()

        if not ders_title:
            raise forms.ValidationError("Ders başlığı gerekli.")

        if aktivite == AktiviteTipi.KONU_ANLATIMI and not detaylar:
            raise forms.ValidationError("Konu Anlatımı için en az bir video/detay seçilmeli.")

        if aktivite in (AktiviteTipi.SORU_COZUMU, AktiviteTipi.TEKRAR) and not detaylar:
            raise forms.ValidationError("Açıklama boş olamaz.")

        cleaned["ders_title"] = ders_title
        return cleaned

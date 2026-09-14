from datetime import date

from django import forms
from django.db.models import Case, IntegerField, Value, When

from .models import BransDeneme, Subject

# Logical display order for BransDeneme subject dropdown.
# Subjects not listed here appear at the end, sorted alphabetically.
_BRANS_SUBJECT_ORDER = {
    'TYT Türkçe':          1,
    'TYT Matematik':       2,
    'TYT Sosyal Bilimler': 3,
    'TYT Fen Bilimleri':   4,
    'TYT Fizik':           5,
    'TYT Kimya':           6,
    'TYT Biyoloji':        7,
    'TYT Problemler':      8,
}


class BransDenemeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ordering = Case(
            *[When(name=name, then=Value(rank)) for name, rank in _BRANS_SUBJECT_ORDER.items()],
            default=Value(100),
            output_field=IntegerField(),
        )
        self.fields['ders'].queryset = (
            Subject.objects
            .annotate(_ord=ordering)
            .order_by('_ord', 'name')
        )

    class Meta:
        model = BransDeneme
        fields = ('ders', 'tarih', 'soru_sayisi', 'dogru', 'yanlis', 'bos', 'sure_dakika', 'ogrenci_notu')
        labels = {
            'ders':         'Ders',
            'tarih':        'Tarih',
            'soru_sayisi':  'Soru Sayısı',
            'dogru':        'Doğru',
            'yanlis':       'Yanlış',
            'bos':          'Boş',
            'sure_dakika':  'Süre (dk)',
            'ogrenci_notu': 'Not',
        }
        widgets = {
            'tarih':        forms.DateInput(attrs={'type': 'date'}),
            'ogrenci_notu': forms.Textarea(attrs={'rows': 2}),
        }

    def clean(self):
        cleaned = super().clean()

        # Non-negative counts
        for field in ('dogru', 'yanlis', 'bos'):
            val = cleaned.get(field)
            if val is not None and val < 0:
                self.add_error(field, 'Değer negatif olamaz.')

        # Duration limits
        sure = cleaned.get('sure_dakika')
        if sure is not None and sure < 0:
            self.add_error('sure_dakika', 'Değer negatif olamaz.')
        if sure is not None and sure > 300:
            self.add_error('sure_dakika', 'Süre 300 dakikayı geçemez.')

        # No future dates
        tarih = cleaned.get('tarih')
        if tarih and tarih > date.today():
            self.add_error('tarih', 'Gelecek bir tarih girilemez.')

        # Total answers must not exceed the effective question count
        ders        = cleaned.get('ders')
        soru_sayisi = cleaned.get('soru_sayisi')
        dogru       = cleaned.get('dogru')  or 0
        yanlis      = cleaned.get('yanlis') or 0
        bos         = cleaned.get('bos')    or 0
        total       = dogru + yanlis + bos
        cap         = soru_sayisi if soru_sayisi else (ders.question_count if ders else None)
        if cap is not None and total > cap:
            raise forms.ValidationError(
                f'Toplam cevap sayısı ({total}), soru sayısını ({cap}) aşıyor.'
            )

        return cleaned

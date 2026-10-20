import re

from django import forms

from .models import Plan

# Sinif and alan choices mirror users_app.models.User.SINIF_CHOICES / ALAN_CHOICES.
# Display labels are more descriptive here for the public form.
SINIF_CHOICES = [
    ('',      'Seçin'),
    ('9',     '9. Sınıf'),
    ('10',    '10. Sınıf'),
    ('11',    '11. Sınıf'),
    ('12',    '12. Sınıf'),
    ('mezun', 'Mezun'),
]

ALAN_CHOICES = [
    ('',    'Henüz seçmedim'),
    ('SAY', 'Sayısal'),
    ('EA',  'Eşit Ağırlık'),
    ('SOZ', 'Sözel'),
    ('DIL', 'Dil'),
]

# Grades for which alan is required — passed to JS via json_script in the template
ALAN_REQUIRED_GRADES = {'11', '12', 'mezun'}


def _normalize_tr_mobile(raw):
    """
    Accept 05xxxxxxxxxx, 5xxxxxxxxxx, +905xxxxxxxxxx, 905xxxxxxxxxx.
    Returns normalized 05xxxxxxxxxx or raises ValueError.
    """
    digits = re.sub(r'[\s\-\(\)\.]+', '', raw)
    if digits.startswith('+90'):
        digits = '0' + digits[3:]
    elif digits.startswith('90') and len(digits) == 12:
        digits = '0' + digits[2:]
    elif re.match(r'^5\d{9}$', digits):
        digits = '0' + digits
    if not re.match(r'^05\d{9}$', digits):
        raise ValueError('invalid turkish mobile')
    return digits


class PurchaseForm(forms.Form):
    full_name = forms.CharField(max_length=255, label='Ad Soyad')
    email     = forms.EmailField(label='E-posta')
    phone     = forms.CharField(
        max_length=32,
        label='Telefon',
        error_messages={'required': 'Telefon numarası zorunludur.'},
        widget=forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}),
    )
    sinif = forms.ChoiceField(
        choices=SINIF_CHOICES,
        label='Sınıf',
        error_messages={'required': 'Sınıf seçimi zorunludur.', 'invalid_choice': 'Geçersiz sınıf.'},
    )
    alan = forms.ChoiceField(
        choices=ALAN_CHOICES,
        label='Alan',
        required=False,
    )
    plan = forms.ModelChoiceField(
        queryset=Plan.objects.filter(active=True),
        label='Plan',
        empty_label=None,
    )
    is_under_18    = forms.BooleanField(required=False, label='18 yaşından küçüğüm')
    guardian_name  = forms.CharField(max_length=255, label='Veli Adı Soyadı', required=False)
    guardian_phone = forms.CharField(max_length=32,  label='Veli Telefonu',   required=False)

    def clean_phone(self):
        raw = (self.cleaned_data.get('phone') or '').strip()
        if not raw:
            raise forms.ValidationError('Telefon numarası zorunludur.')
        try:
            return _normalize_tr_mobile(raw)
        except ValueError:
            raise forms.ValidationError(
                'Geçerli bir Türk cep telefonu numarası girin. Örnek: 0505 123 45 67'
            )

    def clean(self):
        cd = super().clean()
        if cd.get('is_under_18'):
            if not cd.get('guardian_name'):
                self.add_error('guardian_name', '18 yaşından küçükler için veli adı zorunludur.')
            if not cd.get('guardian_phone'):
                self.add_error('guardian_phone', '18 yaşından küçükler için veli telefonu zorunludur.')
        sinif = cd.get('sinif', '')
        if sinif in ALAN_REQUIRED_GRADES and not cd.get('alan', ''):
            self.add_error('alan', '11. sınıf ve üzeri için alan seçimi zorunludur.')
        return cd

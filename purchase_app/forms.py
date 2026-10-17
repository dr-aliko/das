from django import forms

from .models import Plan


class PurchaseForm(forms.Form):
    full_name      = forms.CharField(max_length=255, label='Ad Soyad')
    email          = forms.EmailField(label='E-posta')
    phone          = forms.CharField(max_length=32, label='Telefon', required=False)
    plan           = forms.ModelChoiceField(
        queryset=Plan.objects.filter(active=True),
        label='Plan',
        empty_label=None,
    )
    is_under_18    = forms.BooleanField(required=False, label='18 yaşından küçüğüm')
    guardian_name  = forms.CharField(max_length=255, label='Veli Adı Soyadı', required=False)
    guardian_phone = forms.CharField(max_length=32,  label='Veli Telefonu',   required=False)
    consent_terms  = forms.BooleanField(label='Kullanım Koşullarını okudum ve kabul ediyorum')
    consent_distance = forms.BooleanField(label='Mesafeli Satış Sözleşmesini okudum ve kabul ediyorum')
    consent_kvkk   = forms.BooleanField(label='Kişisel Verilerin Korunması Politikasını okudum ve kabul ediyorum')

    def clean(self):
        cd = super().clean()
        if cd.get('is_under_18'):
            if not cd.get('guardian_name'):
                self.add_error('guardian_name', '18 yaşından küçükler için veli adı zorunludur.')
            if not cd.get('guardian_phone'):
                self.add_error('guardian_phone', '18 yaşından küçükler için veli telefonu zorunludur.')
        return cd

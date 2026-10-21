import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from .models import CoachProfile, StudentInvite, User


# ── IBAN helpers ──────────────────────────────────────────────────────────────

def validate_tr_iban(value):
    """Validate a Turkish IBAN (mod-97). Returns normalised raw string (no spaces)."""
    raw = re.sub(r'\s+', '', (value or '')).upper()
    if not raw.startswith('TR') or len(raw) != 26:
        raise ValidationError(
            'Geçerli bir Türk IBAN numarası girin. Örnek: TR12 3456 7890 1234 5678 9012'
        )
    if not raw[2:].isdigit():
        raise ValidationError('IBAN yalnızca rakam içermelidir (TR sonrası).')
    rearranged = raw[4:] + raw[:4]
    numeric = ''.join(str(ord(c) - ord('A') + 10) if c.isalpha() else c for c in rearranged)
    if int(numeric) % 97 != 1:
        raise ValidationError('IBAN doğrulama hatası (mod-97 kontrolü başarısız).')
    return raw


def mask_iban(iban):
    """Return masked IBAN for display: first 4 chars + **** groups + last 4 chars."""
    if not iban or len(iban) < 8:
        return iban or ''
    head = iban[:4]
    tail = iban[-4:]
    middle_len = len(iban) - 8
    star_groups = ['****'] * ((middle_len + 3) // 4)
    return ' '.join([head] + star_groups + [tail])


# ── Document validation ───────────────────────────────────────────────────────

_ALLOWED_MAGIC = {
    b'%PDF': 'PDF',
    b'\xff\xd8\xff': 'JPEG',
    b'\x89PNG': 'PNG',
}
_MAX_DOCUMENT_BYTES = 5 * 1024 * 1024  # 5 MB


def validate_coach_document(f):
    if f.size > _MAX_DOCUMENT_BYTES:
        raise ValidationError('Dosya boyutu 5 MB\'ı geçemez.')
    f.seek(0)
    header = f.read(8)
    f.seek(0)
    if not any(header.startswith(sig) for sig in _ALLOWED_MAGIC):
        raise ValidationError('Yalnızca PDF, JPG veya PNG dosyası yükleyebilirsiniz.')


class CoachRegistrationForm(forms.Form):
    """Public registration form — creates coach accounts pending admin approval."""
    full_name = forms.CharField(max_length=150, label='Ad Soyad')
    email     = forms.EmailField(label='E-posta')
    phone     = forms.CharField(
        max_length=32,
        label='Telefon',
        widget=forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel', 'placeholder': '0505 123 45 67'}),
    )
    password1 = forms.CharField(widget=forms.PasswordInput, label='Şifre')
    password2 = forms.CharField(widget=forms.PasswordInput, label='Şifre Tekrar')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Bu e-posta adresi zaten kayıtlı.')
        return email

    def clean_phone(self):
        from purchase_app.forms import _normalize_tr_mobile
        try:
            return _normalize_tr_mobile(self.cleaned_data['phone'])
        except ValueError:
            raise forms.ValidationError(
                'Geçerli bir Türk cep telefonu numarası girin. Örnek: 0505 123 45 67'
            )

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Şifreler eşleşmiyor.')
        return p2


class UserRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput, label='Şifre')
    password2 = forms.CharField(widget=forms.PasswordInput, label='Şifre Tekrar')

    class Meta:
        model = User
        fields = ('full_name', 'email', 'role')
        labels = {
            'full_name': 'Ad Soyad',
            'email': 'E-posta',
            'role': 'Hesap Türü',
        }

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Şifreler eşleşmiyor.')
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class InviteStudentForm(forms.Form):
    """Coach fills this to send an invitation to a student."""
    email     = forms.EmailField(label='Öğrenci E-postası')
    full_name = forms.CharField(max_length=150, label='Öğrenci Adı (isteğe bağlı)', required=False)

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Bu e-posta zaten kayıtlı bir kullanıcıya ait.')
        if StudentInvite.objects.filter(email=email, is_used=False).exists():
            raise forms.ValidationError('Bu e-postaya zaten bekleyen bir davet gönderilmiş.')
        return email


class InviteAcceptForm(forms.Form):
    """Student fills this when accepting an invitation."""
    full_name = forms.CharField(max_length=150, label='Ad Soyad')
    password1 = forms.CharField(widget=forms.PasswordInput, label='Şifre')
    password2 = forms.CharField(widget=forms.PasswordInput, label='Şifre Tekrar')
    terms_accepted = forms.BooleanField(
        required=True,
        error_messages={'required': 'Kullanım Koşulları ve Gizlilik Sözleşmesi\'ni kabul etmeniz zorunludur.'},
    )
    kvkk_accepted = forms.BooleanField(
        required=True,
        error_messages={'required': 'KVKK Aydınlatma Metni\'ni kabul etmeniz zorunludur.'},
    )

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Şifreler eşleşmiyor.')
        return p2


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label='E-posta', widget=forms.EmailInput(attrs={'autofocus': True}))


class CoachProfileForm(forms.ModelForm):
    phone = forms.CharField(
        max_length=32,
        required=False,
        label='Telefon',
        widget=forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel', 'placeholder': '0505 123 45 67'}),
    )
    iban = forms.CharField(
        max_length=40,
        required=False,
        label='IBAN',
        widget=forms.TextInput(attrs={'placeholder': 'TR12 3456 7890 1234 5678 9012'}),
    )
    document = forms.FileField(
        required=False,
        label='Kimlik / Sözleşme Belgesi (PDF, JPG, PNG — maks. 5 MB)',
    )

    class Meta:
        model = CoachProfile
        fields = ['phone', 'iban', 'document']

    def clean_phone(self):
        raw = self.cleaned_data.get('phone', '').strip()
        if not raw:
            return ''
        from purchase_app.forms import _normalize_tr_mobile
        try:
            return _normalize_tr_mobile(raw)
        except ValueError:
            raise forms.ValidationError(
                'Geçerli bir Türk cep telefonu numarası girin. Örnek: 0505 123 45 67'
            )

    def clean_iban(self):
        raw = self.cleaned_data.get('iban', '').strip()
        if not raw:
            return ''
        return validate_tr_iban(raw)

    def clean_document(self):
        f = self.cleaned_data.get('document')
        if f:
            validate_coach_document(f)
        return f


class CoachProfileQuickForm(forms.Form):
    """Minimal form used by the non-dismissible popup (name + phone only)."""
    full_name = forms.CharField(max_length=150, label='Ad Soyad')
    phone = forms.CharField(
        max_length=32,
        label='Telefon',
        widget=forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel', 'placeholder': '0505 123 45 67'}),
    )

    def clean_phone(self):
        from purchase_app.forms import _normalize_tr_mobile
        try:
            return _normalize_tr_mobile(self.cleaned_data['phone'])
        except ValueError:
            raise forms.ValidationError(
                'Geçerli bir Türk cep telefonu numarası girin. Örnek: 0505 123 45 67'
            )

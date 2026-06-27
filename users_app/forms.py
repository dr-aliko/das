from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import StudentInvite, User


class CoachRegistrationForm(forms.Form):
    """Public registration form — creates coach accounts pending admin approval."""
    full_name = forms.CharField(max_length=150, label='Ad Soyad')
    email     = forms.EmailField(label='E-posta')
    password1 = forms.CharField(widget=forms.PasswordInput, label='Şifre')
    password2 = forms.CharField(widget=forms.PasswordInput, label='Şifre Tekrar')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Bu e-posta adresi zaten kayıtlı.')
        return email

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

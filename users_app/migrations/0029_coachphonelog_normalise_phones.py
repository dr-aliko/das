"""
0029: Add CoachPhoneLog model and normalise existing coach phone values to +90XXXXXXXXXX.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def normalise_phones(apps, schema_editor):
    """Convert stored phones to +90XXXXXXXXXX format, skipping unrecognised values."""
    import re

    def _to_e164(raw):
        if not raw:
            return raw
        digits = re.sub(r'[\s\-\(\)\.]+', '', raw)
        if digits.startswith('+90') and len(digits) == 13:
            return digits  # already normalised
        if digits.startswith('90') and len(digits) == 12:
            digits = '+90' + digits[2:]
            return digits
        if re.match(r'^05\d{9}$', digits):
            return '+90' + digits[1:]
        if re.match(r'^5\d{9}$', digits):
            return '+90' + digits
        return None  # unrecognised — leave blank rather than store garbage

    CoachProfile = apps.get_model('users_app', 'CoachProfile')
    for cp in CoachProfile.objects.exclude(phone=''):
        normalised = _to_e164(cp.phone)
        if normalised and normalised != cp.phone:
            cp.phone = normalised
            cp.save(update_fields=['phone'])


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0028_coachprofile_coachibanlog'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CoachPhoneLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_phone', models.CharField(blank=True, default='', max_length=20)),
                ('new_phone', models.CharField(max_length=20)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('changed_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('coach', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='phone_logs',
                    to='users_app.coachprofile',
                )),
            ],
            options={
                'verbose_name': 'Telefon Değişiklik Kaydı',
                'verbose_name_plural': 'Telefon Değişiklik Kayıtları',
                'ordering': ['-changed_at'],
            },
        ),
        migrations.RunPython(normalise_phones, migrations.RunPython.noop),
    ]

import users_app.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0027_backfill_coachstudentinterval'),
    ]

    operations = [
        migrations.CreateModel(
            name='CoachProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone', models.CharField(blank=True, default='', max_length=20)),
                ('iban', models.CharField(blank=True, default='', max_length=34)),
                ('document', models.FileField(
                    blank=True,
                    null=True,
                    storage='core_config.private_storage.PrivateFileSystemStorage',
                    upload_to=users_app.models._coach_doc_path,
                )),
                ('document_status', models.CharField(
                    choices=[('pending', 'Bekliyor'), ('approved', 'Onaylandı'), ('rejected', 'Reddedildi')],
                    default='pending',
                    max_length=10,
                )),
                ('document_rejection_reason', models.CharField(blank=True, default='', max_length=500)),
                ('document_reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document_reviewed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('user', models.OneToOneField(
                    limit_choices_to={'role': 'coach'},
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='coach_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Koç Profili',
                'verbose_name_plural': 'Koç Profilleri',
            },
        ),
        migrations.CreateModel(
            name='CoachIbanLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('old_iban_masked', models.CharField(blank=True, default='', max_length=60)),
                ('new_iban_masked', models.CharField(blank=True, default='', max_length=60)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
                ('changed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('coach', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='iban_logs',
                    to='users_app.coachprofile',
                )),
            ],
            options={
                'verbose_name': 'IBAN Değişiklik Kaydı',
                'verbose_name_plural': 'IBAN Değişiklik Kayıtları',
                'ordering': ['-changed_at'],
            },
        ),
    ]

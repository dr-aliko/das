from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_app', '0003_remove_trial_copy'),
    ]

    operations = [
        migrations.CreateModel(
            name='CoachRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=120, verbose_name='Ad Soyad')),
                ('email', models.EmailField(max_length=254, verbose_name='E-posta')),
                ('phone', models.CharField(max_length=30, verbose_name='Telefon')),
                ('grade_level', models.CharField(
                    choices=[('9', '9. Sınıf'), ('10', '10. Sınıf'), ('11', '11. Sınıf'), ('12', '12. Sınıf'), ('mezun', 'Mezun')],
                    max_length=10,
                    verbose_name='Sınıf',
                )),
                ('target_exam_year', models.PositiveSmallIntegerField(verbose_name='Hedef Sınav Yılı')),
                ('track', models.CharField(
                    choices=[('sayisal', 'Sayısal'), ('ea', 'Eşit Ağırlık'), ('sozel', 'Sözel'), ('dil', 'Dil'), ('unknown', 'Henüz belli değil')],
                    max_length=10,
                    verbose_name='Alan',
                )),
                ('note', models.TextField(blank=True, verbose_name='Kısa Not')),
                ('parent_name', models.CharField(blank=True, max_length=120, verbose_name='Veli Adı')),
                ('parent_phone', models.CharField(blank=True, max_length=30, verbose_name='Veli Telefonu')),
                ('status', models.CharField(
                    choices=[('new', 'Yeni'), ('contacted', 'İletişime Geçildi'), ('converted', 'Dönüştürüldü'), ('rejected', 'Reddedildi')],
                    default='new',
                    max_length=12,
                    verbose_name='Durum',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('coach_profile', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='requests',
                    to='marketing_app.coachprofile',
                    verbose_name='Koç',
                )),
            ],
            options={
                'verbose_name': 'Koç Talebi',
                'verbose_name_plural': 'Koç Talepleri',
                'ordering': ['-created_at'],
            },
        ),
    ]

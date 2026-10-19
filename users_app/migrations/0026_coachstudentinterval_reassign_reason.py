from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0025_notification_hidden_by_user'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='coachstudent',
            name='deactivation_reason',
            field=models.CharField(
                blank=True,
                choices=[
                    ('manual', 'Koç tarafından kaldırıldı'),
                    ('payment_overdue', 'Ödeme gecikmesi'),
                    ('reassign', 'Koç değiştirildi'),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name='CoachStudentInterval',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(blank=True, max_length=10, null=True)),
                ('started_at', models.DateTimeField()),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('close_reason', models.CharField(
                    blank=True,
                    choices=[
                        ('manual', 'Manuel kapatıldı'),
                        ('payment_overdue', 'Ödeme gecikmesi'),
                        ('reassign', 'Koç değiştirildi'),
                        ('backfill', 'Geriye dönük dolduruldu'),
                    ],
                    max_length=20,
                    null=True,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('coach', models.ForeignKey(
                    limit_choices_to={'role': 'coach'},
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='coach_intervals',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('student', models.ForeignKey(
                    limit_choices_to={'role': 'student'},
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='student_intervals',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Koç-Öğrenci Dönemi',
                'verbose_name_plural': 'Koç-Öğrenci Dönemleri',
                'indexes': [
                    models.Index(fields=['student', 'started_at'], name='users_app_c_student_started_idx'),
                    models.Index(fields=['coach', 'started_at'], name='users_app_c_coach_started_idx'),
                ],
            },
        ),
    ]

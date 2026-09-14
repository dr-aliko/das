from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_from_user_flag(apps, schema_editor):
    """
    Students who had the global sr_enabled=False get a disabled setting
    for every subject they already have topic progress in.
    Students with sr_enabled=True get no rows (absence == enabled by default).
    """
    User = apps.get_model('users_app', 'User')
    StudentTopicProgress = apps.get_model('konu_takip_app', 'StudentTopicProgress')
    StudentSubjectSrSetting = apps.get_model('konu_takip_app', 'StudentSubjectSrSetting')

    for student in User.objects.filter(role='student', sr_enabled=False):
        subject_ids = (
            StudentTopicProgress.objects
            .filter(student=student)
            .values_list('topic__subject', flat=True)
            .distinct()
        )
        for subject_id in subject_ids:
            if subject_id is not None:
                StudentSubjectSrSetting.objects.get_or_create(
                    student=student,
                    subject_id=subject_id,
                    defaults={'sr_enabled': False},
                )


class Migration(migrations.Migration):

    dependencies = [
        ('konu_takip_app', '0002_studenttopicprogress_spaced_repetition'),
        ('exams_app', '__first__'),
        ('users_app', '0016_user_sr_enabled'),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentSubjectSrSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sr_enabled', models.BooleanField(default=True)),
                ('student', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='subject_sr_settings',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('subject', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='student_sr_settings',
                    to='exams_app.subject',
                )),
            ],
            options={'unique_together': {('student', 'subject')}},
        ),
        migrations.RunPython(seed_from_user_flag, migrations.RunPython.noop),
    ]

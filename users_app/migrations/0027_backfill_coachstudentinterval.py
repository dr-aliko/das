from django.db import migrations
from django.utils import timezone


def backfill_intervals(apps, schema_editor):
    CoachStudent = apps.get_model('users_app', 'CoachStudent')
    CoachStudentInterval = apps.get_model('users_app', 'CoachStudentInterval')
    now = timezone.now()
    rows = []
    for link in CoachStudent.objects.all():
        if link.active:
            rows.append(CoachStudentInterval(
                coach_id=link.coach_id,
                student_id=link.student_id,
                source=link.source,
                started_at=link.created_at,
                ended_at=None,
                close_reason=None,
            ))
        else:
            rows.append(CoachStudentInterval(
                coach_id=link.coach_id,
                student_id=link.student_id,
                source=link.source,
                started_at=link.created_at,
                ended_at=now,
                close_reason='backfill',
            ))
    CoachStudentInterval.objects.bulk_create(rows)


def reverse_backfill(apps, schema_editor):
    CoachStudentInterval = apps.get_model('users_app', 'CoachStudentInterval')
    CoachStudentInterval.objects.filter(close_reason='backfill').delete()
    CoachStudentInterval.objects.filter(ended_at__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0026_coachstudentinterval_reassign_reason'),
    ]

    operations = [
        migrations.RunPython(backfill_intervals, reverse_code=reverse_backfill),
    ]

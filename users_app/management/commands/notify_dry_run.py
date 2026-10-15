"""
python manage.py notify_dry_run
python manage.py notify_dry_run --task deadline
python manage.py notify_dry_run --task motivational
python manage.py notify_dry_run --task konu

Read-only: prints how many students each scheduled notification task would select
right now, and their user IDs. Does not create any Notification rows.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Dry-run student notification tasks — prints recipient counts without sending.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--task',
            choices=['deadline', 'motivational', 'konu', 'all'],
            default='all',
            help='Which task to simulate (default: all)',
        )

    def handle(self, *args, **options):
        task = options['task']
        if task in ('deadline', 'all'):
            self._dry_deadline()
        if task in ('motivational', 'all'):
            self._dry_motivational()
        if task in ('konu', 'all'):
            self._dry_konu()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _active_students(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.filter(role='student', is_active=True)

    def _dry_deadline(self):
        from django.utils.timezone import localdate
        from tasks_app.models import GorevGrubu

        today = localdate()
        students = self._active_students()
        recipients = []
        skipped_no_tasks = 0

        for student in students:
            pending = GorevGrubu.objects.filter(
                student=student,
                tarih=today,
                is_completed=False,
                is_hidden_by_student=False,
            ).count()
            if pending == 0:
                skipped_no_tasks += 1
                continue
            recipients.append((student.id, pending))

        self.stdout.write(self.style.SUCCESS(
            f'\n[deadline 09:00] {len(recipients)} recipient(s) '
            f'({skipped_no_tasks} skipped — no pending tasks today)'
        ))
        for uid, count in recipients:
            self.stdout.write(f'  user_id={uid}  pending_tasks={count}')

    def _dry_motivational(self):
        from django.utils.timezone import localdate
        from tasks_app.models import GorevGrubu

        today = localdate()
        students = self._active_students()
        recipients = []
        skipped_all_done = 0

        for student in students:
            today_tasks = GorevGrubu.objects.filter(
                student=student,
                tarih=today,
                is_hidden_by_student=False,
            )
            if today_tasks.exists() and not today_tasks.filter(is_completed=False).exists():
                skipped_all_done += 1
                continue
            recipients.append(student.id)

        self.stdout.write(self.style.SUCCESS(
            f'\n[motivational 19:00] {len(recipients)} recipient(s) '
            f'({skipped_all_done} skipped — all tasks already done)'
        ))
        for uid in recipients:
            self.stdout.write(f'  user_id={uid}')

    def _dry_konu(self):
        from django.utils import timezone
        from konu_takip_app.models import StudentSubjectSrSetting, StudentTopicProgress

        now = timezone.now()
        students = self._active_students()
        recipients = []
        skipped_no_sr = 0
        skipped_no_due = 0

        for student in students:
            enabled_subjects = set(
                StudentSubjectSrSetting.objects
                .filter(student=student, sr_enabled=True)
                .values_list('subject_id', flat=True)
            )
            if not enabled_subjects:
                skipped_no_sr += 1
                continue
            due_count = StudentTopicProgress.objects.filter(
                student=student, finished=True, next_review_at__lte=now,
                topic__subject_id__in=enabled_subjects,
            ).count()
            if due_count == 0:
                skipped_no_due += 1
                continue
            recipients.append((student.id, due_count))

        self.stdout.write(self.style.SUCCESS(
            f'\n[konu_review 08:00] {len(recipients)} recipient(s) '
            f'({skipped_no_sr} skipped — SR disabled; {skipped_no_due} skipped — nothing due)'
        ))
        for uid, count in recipients:
            self.stdout.write(f'  user_id={uid}  due_topics={count}')

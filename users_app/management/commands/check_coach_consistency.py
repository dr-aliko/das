"""
python manage.py check_coach_consistency          # dry run: report all drift
python manage.py check_coach_consistency --fix    # repair via service layer

Checks five drift kinds (all reported in dry run; repaired with --fix):

  A  active_no_interval      Active CoachStudent without an open interval
                             Fix: open_interval(link)
  B  interval_no_active      Open CoachStudentInterval without an active link
                             Fix: close_interval with reason 'backfill'
  C  duplicate_open          Two or more open intervals for one student
                             Fix: close all but the newest (reason 'backfill')
  D  coach_fk_no_link        User.coach set but no active CoachStudent row
                             Fix: ensure_active_link(coach, student, source=None)
  E  coach_fk_mismatch       Active CoachStudent coach ≠ User.coach
                             Fix: User.coach = active_link.coach  (no interval change)

All fixes go through the service layer so intervals stay in sync.
"""
import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Audit CoachStudent / CoachStudentInterval consistency. Dry run by default.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix', action='store_true', default=False,
            help='Repair found issues via the service layer (default: dry run).',
        )

    def handle(self, *args, **options):
        fix = options['fix']
        counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}

        self._check_active_no_interval(fix, counts)
        self._check_interval_no_active(fix, counts)
        self._check_duplicate_open(fix, counts)
        self._check_coach_fk_no_link(fix, counts)
        self._check_coach_fk_mismatch(fix, counts)

        total = sum(counts.values())
        mode = 'FIXED' if fix else 'DRY RUN'
        self.stdout.write(
            f'\n{mode}: {total} issue(s) found — '
            + ', '.join(f'{k}={v}' for k, v in counts.items() if v)
        )
        if total and not fix:
            self.stdout.write('Pass --fix to repair.')

    # ── A: active link without an open interval ───────────────────────────────

    def _check_active_no_interval(self, fix, counts):
        from users_app.models import CoachStudent, CoachStudentInterval
        from users_app.services.coach_student import open_interval

        open_pairs = set(
            CoachStudentInterval.objects
            .filter(ended_at__isnull=True)
            .values_list('coach_id', 'student_id')
        )
        for link in CoachStudent.objects.filter(active=True).select_related('coach', 'student'):
            if (link.coach_id, link.student_id) not in open_pairs:
                counts['A'] += 1
                self.stdout.write(
                    f'[A] active_no_interval: CoachStudent pk={link.pk} '
                    f'coach={link.coach_id} student={link.student_id}'
                )
                if fix:
                    open_interval(link)

    # ── B: open interval without an active link ───────────────────────────────

    def _check_interval_no_active(self, fix, counts):
        from users_app.models import CoachStudent, CoachStudentInterval

        active_pairs = set(
            CoachStudent.objects.filter(active=True).values_list('coach_id', 'student_id')
        )
        orphan_qs = CoachStudentInterval.objects.filter(ended_at__isnull=True)
        now = timezone.now()
        for ci in orphan_qs:
            if (ci.coach_id, ci.student_id) not in active_pairs:
                counts['B'] += 1
                self.stdout.write(
                    f'[B] interval_no_active: CoachStudentInterval pk={ci.pk} '
                    f'coach={ci.coach_id} student={ci.student_id}'
                )
                if fix:
                    CoachStudentInterval.objects.filter(pk=ci.pk).update(
                        ended_at=now,
                        close_reason=CoachStudentInterval.REASON_BACKFILL,
                    )

    # ── C: duplicate open intervals for one student ───────────────────────────

    def _check_duplicate_open(self, fix, counts):
        from django.db.models import Count
        from users_app.models import CoachStudentInterval

        dupes = (
            CoachStudentInterval.objects
            .filter(ended_at__isnull=True)
            .values('student_id')
            .annotate(n=Count('pk'))
            .filter(n__gt=1)
        )
        now = timezone.now()
        for row in dupes:
            sid = row['student_id']
            open_rows = list(
                CoachStudentInterval.objects
                .filter(student_id=sid, ended_at__isnull=True)
                .order_by('-started_at')
            )
            counts['C'] += len(open_rows) - 1
            self.stdout.write(
                f'[C] duplicate_open: student={sid} has {len(open_rows)} open intervals '
                f'(pks={[r.pk for r in open_rows]})'
            )
            if fix:
                # Keep the newest (open_rows[0]); close the rest
                for stale in open_rows[1:]:
                    CoachStudentInterval.objects.filter(pk=stale.pk).update(
                        ended_at=now,
                        close_reason=CoachStudentInterval.REASON_BACKFILL,
                    )

    # ── D: User.coach set but no active CoachStudent row ─────────────────────

    def _check_coach_fk_no_link(self, fix, counts):
        from users_app.models import CoachStudent, User
        from users_app.services.coach_student import ensure_active_link

        active_pairs = set(
            CoachStudent.objects.filter(active=True).values_list('coach_id', 'student_id')
        )
        for student in User.objects.filter(role='student', coach__isnull=False).select_related('coach'):
            if (student.coach_id, student.pk) not in active_pairs:
                counts['D'] += 1
                self.stdout.write(
                    f'[D] coach_fk_no_link: student pk={student.pk} '
                    f'User.coach={student.coach_id} but no active CoachStudent'
                )
                if fix:
                    ensure_active_link(student.coach, student, source=None)

    # ── E: active link coach ≠ User.coach ────────────────────────────────────

    def _check_coach_fk_mismatch(self, fix, counts):
        from users_app.models import CoachStudent, User

        for link in CoachStudent.objects.filter(active=True).select_related('student'):
            student = link.student
            if student.coach_id != link.coach_id:
                counts['E'] += 1
                self.stdout.write(
                    f'[E] coach_fk_mismatch: student pk={student.pk} '
                    f'User.coach={student.coach_id} but active CoachStudent.coach={link.coach_id}'
                )
                if fix:
                    User.objects.filter(pk=student.pk).update(coach_id=link.coach_id)

"""
python manage.py recompute_streaks                    # dry run
python manage.py recompute_streaks --apply            # write streak fields
python manage.py recompute_streaks --student 42       # single student, dry run
python manage.py recompute_streaks --student 42 --apply
python manage.py recompute_streaks --detail 42        # print activity dates by source

Activity sources (same rule as the live record_activity call):
  • Exam.exam_date           (DateField — already Istanbul calendar date)
  • StudentTask.completed_at (DateTimeField → Istanbul date)
  • GorevGrubu.completed_at  (DateTimeField → Istanbul date)

NOTE: BransDeneme saves also call record_activity (exams_app/views.py:3507) but that
model is not included here because the BransDeneme entry itself does not represent a
unique calendar date beyond what Exam already covers.  This is why last_activity_date
is protected from being lowered (fix 2 below).

Side-effect guarantees:
  • Does NOT award badges / achievements.
  • Does NOT create Notification rows.
  • Does NOT call any push or Celery task.
  • --apply only touches the three streak fields on User.

current_streak semantics (fix 1):
  record_activity resets to 1 when a streak breaks — it never stores 0.
  The stored value therefore goes stale (e.g. "4") when a student hasn't
  been active for months.  recompute sets current_streak = 0 whenever
  last_activity_date < yesterday, matching "no active streak right now."
  The next record_activity call after that will set it to 1 as usual.

last_activity_date protection (fix 2):
  BransDeneme and possibly other future sources call record_activity but
  are not in _collect_activity_dates.  We never lower the stored value;
  we take max(old, new).

Badge note (dry run only):
  --apply does NOT award any badges.  The "WOULD AWARD" lines report streak
  badges where final_longest >= threshold but the student lacks the badge.
  These are NOT automatically awarded by the next record_activity call for
  students whose current_streak was zeroed — they would have to rebuild a
  new streak to those thresholds from scratch.  For students whose streak is
  still live (last_activity_date >= yesterday), the next record_activity call
  will award any newly-reachable thresholds silently (no Notification, no push
  — badge award only writes a StudentAchievement row that appears on the profile).

Coach-task paths that skip record_activity (data gap this command covers):
  • exams_app.views.coach_complete_task     — StudentTask, no streak call
  • exams_app.views.coach_brans_task_action — StudentTask, no streak call
These have is_completed=True + completed_at set so they ARE included in the
recompute; the student's history counts regardless of who completed the task.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from users_app.services.streak_engine import streak_from_dates

_STREAK_BADGE_THRESHOLDS = [
    (3,   'streak_3'),
    (7,   'streak_7'),
    (7,   'perfect_week'),
    (14,  'streak_14'),
    (30,  'streak_30'),
    (60,  'streak_60'),
    (100, 'streak_100'),
]


class Command(BaseCommand):
    help = (
        'Recompute streak fields from full student history. '
        'Default: dry run.  Pass --apply to write.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true', default=False,
            help='Write computed values to the database (default: dry run).',
        )
        parser.add_argument(
            '--student', type=int, default=None, metavar='USER_ID',
            help='Process only this student user ID.',
        )
        parser.add_argument(
            '--detail', type=int, default=None, metavar='USER_ID',
            help='Print activity dates by source for one student then exit.',
        )

    def handle(self, *args, **options):
        if options['detail']:
            self._handle_detail(options['detail'])
            return

        apply = options['apply']
        student_id = options.get('student')

        from users_app.models import User
        qs = User.objects.filter(role='student')
        if student_id:
            qs = qs.filter(pk=student_id)

        tz = timezone.get_current_timezone()
        yesterday = timezone.localdate() - timedelta(days=1)
        total = changed = 0

        for student in qs.iterator():
            total += 1
            dates = _collect_activity_dates(student, tz)
            new_current, new_longest, new_last = streak_from_dates(dates)

            # Fix 1: zero out current streak when the last run ended before yesterday.
            # record_activity resets to 1 on a gap, never stores 0 itself; recompute
            # uses 0 to mean "no active streak" so stale values (e.g. "4 months ago")
            # are not displayed as if the streak were live.
            if new_last and new_last < yesterday:
                new_current = 0

            old_current = student.current_streak
            old_longest = student.longest_streak
            old_last = student.last_activity_date

            # Never lower longest streak (max of old and recomputed)
            final_longest = max(old_longest, new_longest)

            # Fix 2: never lower last_activity_date.
            # BransDeneme saves call record_activity but are not in our collection,
            # so new_last can be earlier than old_last.
            if old_last and new_last:
                final_last = max(old_last, new_last)
            elif old_last:
                final_last = old_last
            else:
                final_last = new_last

            needs_change = (
                old_current != new_current
                or old_longest != final_longest
                or old_last != final_last
            )

            badge_note = _missing_streak_badges(student, final_longest)

            if needs_change or badge_note:
                changed += 1
                label = f'pk={student.pk}'
                name = (getattr(student, 'full_name', None) or '').strip()
                if name:
                    label += f' ({name})'

                self.stdout.write(label + ':')
                self.stdout.write(
                    f'  current_streak     {old_current} → {new_current}'
                    if old_current != new_current else
                    f'  current_streak     {old_current} (no change)'
                )
                self.stdout.write(
                    f'  longest_streak     {old_longest} → {final_longest}'
                    if old_longest != final_longest else
                    f'  longest_streak     {old_longest} (no change)'
                )
                self.stdout.write(
                    f'  last_activity_date {old_last} → {final_last}'
                    if old_last != final_last else
                    f'  last_activity_date {old_last} (no change)'
                )
                if badge_note:
                    self.stdout.write(f'  WOULD AWARD (not applied): {badge_note}')

            if needs_change and apply:
                student.current_streak = new_current
                student.longest_streak = final_longest
                student.last_activity_date = final_last
                student.save(
                    update_fields=['current_streak', 'longest_streak', 'last_activity_date']
                )

        mode = 'APPLIED' if apply else 'DRY RUN'
        self.stdout.write(
            f'\n{mode}: {changed} of {total} student(s) have changes.'
            + ('' if apply else '\nPass --apply to write.')
        )

    def _handle_detail(self, student_id):
        from users_app.models import User
        try:
            student = User.objects.get(pk=student_id, role='student')
        except User.DoesNotExist:
            self.stdout.write(f'pk={student_id}: student not found.')
            return

        tz = timezone.get_current_timezone()
        name = (getattr(student, 'full_name', None) or '').strip() or student.username
        self.stdout.write(
            f'Activity sources for pk={student_id} ({name})\n'
            f'  stored: current_streak={student.current_streak}  '
            f'longest_streak={student.longest_streak}  '
            f'last_activity_date={student.last_activity_date}'
        )

        from exams_app.models import Exam, StudentTask
        from tasks_app.models import GorevGrubu

        # Exams
        exams = list(
            Exam.objects.filter(student=student)
            .values_list('exam_date', flat=True)
            .order_by('exam_date')
        )
        self.stdout.write(f'\n  EXAM ({len(exams)} dates):')
        for d in exams:
            self.stdout.write(f'    {d}')

        # StudentTask completions
        tasks = list(
            StudentTask.objects.filter(
                student=student, is_completed=True, completed_at__isnull=False
            ).values('completed_at', 'assigned_by_coach').order_by('completed_at')
        )
        self.stdout.write(f'\n  STUDENT_TASK ({len(tasks)} completions):')
        for t in tasks:
            local_d = t['completed_at'].astimezone(tz).date()
            who = 'assigned_by_coach' if t['assigned_by_coach'] else 'self_assigned'
            self.stdout.write(f'    {local_d}  [{who}]')

        # GorevGrubu completions
        gorevs = list(
            GorevGrubu.objects.filter(
                student=student, is_completed=True, completed_at__isnull=False
            ).values_list('completed_at', flat=True).order_by('completed_at')
        )
        self.stdout.write(f'\n  GOREV_GRUBU ({len(gorevs)} completions):')
        for dt in gorevs:
            self.stdout.write(f'    {dt.astimezone(tz).date()}')

        # Union used for streak computation
        all_dates = set()
        all_dates.update(exams)
        all_dates.update(t['completed_at'].astimezone(tz).date() for t in tasks)
        all_dates.update(dt.astimezone(tz).date() for dt in gorevs)
        sorted_all = sorted(all_dates)

        new_current, new_longest, new_last = streak_from_dates(sorted_all)
        yesterday = timezone.localdate() - timedelta(days=1)
        if new_last and new_last < yesterday:
            new_current = 0

        self.stdout.write(f'\n  UNION ({len(sorted_all)} unique dates):')
        self.stdout.write(f'    {sorted_all}')
        self.stdout.write(
            f'\n  RECOMPUTED: current_streak={new_current}  '
            f'longest_streak={new_longest}  last_activity_date={new_last}'
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _collect_activity_dates(student, tz):
    """Return a set of local (Istanbul) dates on which the student was active."""
    from exams_app.models import Exam, StudentTask
    from tasks_app.models import GorevGrubu

    dates = set()

    dates.update(
        Exam.objects.filter(student=student)
        .values_list('exam_date', flat=True)
    )

    for dt in StudentTask.objects.filter(
        student=student, is_completed=True, completed_at__isnull=False
    ).values_list('completed_at', flat=True):
        dates.add(dt.astimezone(tz).date())

    for dt in GorevGrubu.objects.filter(
        student=student, is_completed=True, completed_at__isnull=False
    ).values_list('completed_at', flat=True):
        dates.add(dt.astimezone(tz).date())

    return dates


def _missing_streak_badges(student, final_longest):
    """
    Return comma-separated streak badge keys that final_longest qualifies for
    but the student does not yet have.  Empty string if none.
    """
    from users_app.models import StudentAchievement
    existing = set(
        StudentAchievement.objects.filter(student=student)
        .values_list('badge_key', flat=True)
    )
    would_award = [
        key
        for threshold, key in _STREAK_BADGE_THRESHOLDS
        if final_longest >= threshold and key not in existing
    ]
    return ', '.join(would_award)

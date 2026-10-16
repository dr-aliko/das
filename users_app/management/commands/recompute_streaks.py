"""
python manage.py recompute_streaks            # dry run — prints diffs, writes nothing
python manage.py recompute_streaks --apply    # writes current_streak, longest_streak,
                                              #   last_activity_date (never lowers longest)
python manage.py recompute_streaks --student 42 [--apply]  # single student

Activity sources (same rule as the live record_activity call):
  • Exam.exam_date           (DateField — already Istanbul calendar date)
  • StudentTask.completed_at (DateTimeField — converted to Istanbul date)
  • GorevGrubu.completed_at  (DateTimeField — converted to Istanbul date)

Side-effect guarantees:
  • Does NOT award badges / achievements.
  • Does NOT create Notification rows.
  • Does NOT call any push or Celery task.
  • --apply only touches the three streak fields on User.

Coach-task paths that currently skip record_activity (data gap this command fixes):
  • exams_app.views.coach_complete_task     — marks StudentTask complete, no streak call
  • exams_app.views.coach_brans_task_action — action='complete', no streak call
These coach completions are included in the recompute (they have is_completed=True +
completed_at), which is correct: the student's history counts regardless of who completed.
"""
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
        'Default: dry run. Pass --apply to write.'
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

    def handle(self, *args, **options):
        apply = options['apply']
        student_id = options.get('student')

        from users_app.models import User
        qs = User.objects.filter(role='student')
        if student_id:
            qs = qs.filter(pk=student_id)

        tz = timezone.get_current_timezone()
        total = changed = 0

        for student in qs.iterator():
            total += 1
            dates = _collect_activity_dates(student, tz)
            new_current, new_longest, new_last = streak_from_dates(dates)

            old_current = student.current_streak
            old_longest = student.longest_streak
            old_last = student.last_activity_date

            # Never lower a longest streak that was earned earlier
            final_longest = max(old_longest, new_longest)

            needs_change = (
                old_current != new_current
                or old_longest != final_longest
                or old_last != new_last
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
                    f'  last_activity_date {old_last} → {new_last}'
                    if old_last != new_last else
                    f'  last_activity_date {old_last} (no change)'
                )
                if badge_note:
                    self.stdout.write(
                        f'  WOULD AWARD (not applied): {badge_note}'
                    )

            if needs_change and apply:
                student.current_streak = new_current
                student.longest_streak = final_longest
                student.last_activity_date = new_last
                student.save(
                    update_fields=['current_streak', 'longest_streak', 'last_activity_date']
                )

        mode = 'APPLIED' if apply else 'DRY RUN'
        self.stdout.write(
            f'\n{mode}: {changed} of {total} student(s) have changes.'
            + ('' if apply else '\nPass --apply to write.')
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _collect_activity_dates(student, tz):
    """Return a set of local (Istanbul) dates on which the student was active."""
    from exams_app.models import Exam, StudentTask
    from tasks_app.models import GorevGrubu

    dates = set()

    # Exams: exam_date is a DateField entered by the user — treat as local date directly
    dates.update(
        Exam.objects.filter(student=student)
        .values_list('exam_date', flat=True)
    )

    # StudentTask completions: timezone-aware datetime → Istanbul date
    for dt in StudentTask.objects.filter(
        student=student, is_completed=True, completed_at__isnull=False
    ).values_list('completed_at', flat=True):
        dates.add(dt.astimezone(tz).date())

    # GorevGrubu completions: timezone-aware datetime → Istanbul date
    for dt in GorevGrubu.objects.filter(
        student=student, is_completed=True, completed_at__isnull=False
    ).values_list('completed_at', flat=True):
        dates.add(dt.astimezone(tz).date())

    return dates


def _missing_streak_badges(student, final_longest):
    """
    Return a comma-separated string of streak badge keys that final_longest
    qualifies for but the student does not yet have.  Empty string if none.
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

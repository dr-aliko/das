"""
Tests for the recompute_streaks management command and streak_from_dates helper.

Coverage:
  - streak_from_dates basic correctness
  - rule parity: streak_from_dates agrees with replaying record_activity event-by-event
  - midnight Istanbul boundary: 21:30 UTC = 00:30 Istanbul lands on the Istanbul date
  - dry run writes nothing
  - --apply writes streak fields only
  - longest streak is never lowered
  - no Notification rows created
  - no StudentAchievement rows created
"""
import pytest
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.core.management import call_command
from model_bakery import baker

from users_app.services.streak_engine import streak_from_dates


# ── streak_from_dates unit tests ──────────────────────────────────────────────

def test_streak_from_dates_empty():
    assert streak_from_dates([]) == (0, 0, None)
    assert streak_from_dates([None, None]) == (0, 0, None)


def test_streak_from_dates_single_day():
    d = date(2024, 1, 15)
    assert streak_from_dates([d]) == (1, 1, d)


def test_streak_from_dates_consecutive():
    dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
    current, longest, last = streak_from_dates(dates)
    assert current == 3
    assert longest == 3
    assert last == date(2024, 1, 3)


def test_streak_from_dates_gap_resets():
    dates = [
        date(2024, 1, 1),
        date(2024, 1, 2),
        # gap: Jan 3 missing
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 6),
    ]
    current, longest, last = streak_from_dates(dates)
    assert current == 3     # Jan 4-5-6
    assert longest == 3
    assert last == date(2024, 1, 6)


def test_streak_from_dates_longest_from_earlier_run():
    dates = [
        date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4),  # 4-day run
        # gap
        date(2024, 1, 10), date(2024, 1, 11),  # 2-day run at end
    ]
    current, longest, last = streak_from_dates(dates)
    assert current == 2    # most-recent run
    assert longest == 4    # best run ever
    assert last == date(2024, 1, 11)


def test_streak_from_dates_deduplicates():
    d = date(2024, 3, 1)
    assert streak_from_dates([d, d, d]) == (1, 1, d)


# ── Parity: streak_from_dates agrees with record_activity ────────────────────

@pytest.mark.django_db
def test_parity_with_record_activity():
    """
    Replaying record_activity once per date produces the same result as
    streak_from_dates called with the same date list.
    Both must use the same consecutive-day rule.
    """
    student = baker.make(
        'users_app.User', role='student', is_active=True,
        current_streak=0, last_activity_date=None, longest_streak=0,
    )

    activity_dates = [
        date(2024, 2, 1),
        date(2024, 2, 2),
        date(2024, 2, 3),
        # gap on 2024-02-04
        date(2024, 2, 5),
        date(2024, 2, 6),
    ]

    from users_app.services.streak_engine import record_activity
    for d in activity_dates:
        with patch('users_app.services.streak_engine.timezone') as mock_tz:
            mock_tz.localdate.return_value = d
            mock_tz.timedelta = timedelta
            record_activity(student)

    student.refresh_from_db()

    computed_current, computed_longest, computed_last = streak_from_dates(activity_dates)
    assert student.current_streak == computed_current
    assert student.longest_streak == computed_longest
    assert student.last_activity_date == computed_last


# ── Midnight Istanbul boundary ────────────────────────────────────────────────

@pytest.mark.django_db
def test_gorevgrubu_midnight_istanbul_boundary():
    """
    A GorevGrubu completed at 21:30 UTC = 00:30 Istanbul (March 16)
    must contribute date(2024, 3, 16) to the student's activity dates,
    not date(2024, 3, 15).
    """
    student = baker.make(
        'users_app.User', role='student', is_active=True,
        current_streak=0, last_activity_date=None, longest_streak=0,
    )
    istanbul_date = date(2024, 3, 16)
    utc_dt = datetime(2024, 3, 15, 21, 30, tzinfo=dt_timezone.utc)

    from tasks_app.models import GorevGrubu
    GorevGrubu.objects.create(
        student=student,
        tarih=istanbul_date,
        ders_title='Fizik',
        aktivite_tipi='tekrar',
        is_completed=True,
        completed_at=utc_dt,
    )

    from django.utils import timezone as dj_tz
    from users_app.management.commands.recompute_streaks import _collect_activity_dates
    tz = dj_tz.get_current_timezone()
    dates = _collect_activity_dates(student, tz)

    assert istanbul_date in dates, (
        'GorevGrubu at 21:30 UTC (= 00:30 Istanbul next day) '
        'must map to the Istanbul date, not the UTC date.'
    )
    assert date(2024, 3, 15) not in dates


# ── Dry run writes nothing ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_dry_run_does_not_write(capsys):
    """Without --apply the command prints diffs but does not save to DB."""
    student = baker.make(
        'users_app.User', role='student', is_active=True,
        current_streak=0, last_activity_date=None, longest_streak=0,
    )
    baker.make('exams_app.Exam', student=student, exam_date=date(2024, 5, 1))
    baker.make('exams_app.Exam', student=student, exam_date=date(2024, 5, 2))

    call_command('recompute_streaks', student=student.pk)

    student.refresh_from_db()
    assert student.current_streak == 0     # unchanged
    assert student.last_activity_date is None


# ── --apply writes streak fields ─────────────────────────────────────────────

@pytest.mark.django_db
def test_apply_writes_streak_fields():
    """--apply updates current_streak, longest_streak, last_activity_date."""
    student = baker.make(
        'users_app.User', role='student', is_active=True,
        current_streak=0, last_activity_date=None, longest_streak=0,
    )
    baker.make('exams_app.Exam', student=student, exam_date=date(2024, 5, 10))
    baker.make('exams_app.Exam', student=student, exam_date=date(2024, 5, 11))
    baker.make('exams_app.Exam', student=student, exam_date=date(2024, 5, 12))

    call_command('recompute_streaks', student=student.pk, apply=True)

    student.refresh_from_db()
    assert student.current_streak == 3
    assert student.longest_streak == 3
    assert student.last_activity_date == date(2024, 5, 12)


# ── longest streak never lowered ─────────────────────────────────────────────

@pytest.mark.django_db
def test_longest_streak_never_lowered():
    """If the stored longest_streak is higher than recomputed, keep the stored value."""
    student = baker.make(
        'users_app.User', role='student', is_active=True,
        current_streak=50, last_activity_date=date(2024, 1, 1), longest_streak=50,
    )
    # Only 2 days of history — recomputed longest would be 2
    baker.make('exams_app.Exam', student=student, exam_date=date(2024, 5, 1))
    baker.make('exams_app.Exam', student=student, exam_date=date(2024, 5, 2))

    call_command('recompute_streaks', student=student.pk, apply=True)

    student.refresh_from_db()
    assert student.longest_streak == 50    # must not be lowered to 2


# ── no Notification rows created ─────────────────────────────────────────────

@pytest.mark.django_db
def test_no_notifications_created():
    """The command must never create Notification rows."""
    from users_app.models import Notification
    student = baker.make(
        'users_app.User', role='student', is_active=True,
        current_streak=0, last_activity_date=None, longest_streak=0,
    )
    for d in range(1, 8):
        baker.make('exams_app.Exam', student=student, exam_date=date(2024, 6, d))

    before = Notification.objects.count()
    call_command('recompute_streaks', student=student.pk, apply=True)
    assert Notification.objects.count() == before


# ── no StudentAchievement rows created ───────────────────────────────────────

@pytest.mark.django_db
def test_no_achievements_created():
    """The command must not award badges even when thresholds are crossed."""
    from users_app.models import StudentAchievement
    student = baker.make(
        'users_app.User', role='student', is_active=True,
        current_streak=0, last_activity_date=None, longest_streak=0,
    )
    for d in range(1, 8):
        baker.make('exams_app.Exam', student=student, exam_date=date(2024, 7, d))

    before = StudentAchievement.objects.filter(student=student).count()
    call_command('recompute_streaks', student=student.pk, apply=True)
    assert StudentAchievement.objects.filter(student=student).count() == before

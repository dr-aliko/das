"""
Tests for compute_split:
- single coach full period
- 10+20 worked example -> A 83333, B 166667
- 7+8+15 worked example -> remainder to last
- gap case (days with no coach paid to nobody)
- entire-period gap fallback
"""
import pytest
from datetime import date, timedelta

from django.utils import timezone
from model_bakery import baker

from users_app.models import CoachStudent, CoachStudentInterval, User
from earnings_app.services import compute_split


def make_coach(**kw):
    return baker.make(User, role='coach', is_active=True, is_approved=True, **kw)


def make_student(**kw):
    return baker.make(User, role='student', is_active=True, **kw)


def make_interval(coach, student, start_date, end_date=None, source='vagus'):
    from datetime import datetime, time
    from django.utils.timezone import make_aware
    started_at = make_aware(datetime.combine(start_date, time.min))
    ended_at = make_aware(datetime.combine(end_date, time.min)) if end_date else None
    return baker.make(
        CoachStudentInterval,
        coach=coach, student=student,
        source=source,
        started_at=started_at,
        ended_at=ended_at,
    )


@pytest.mark.django_db
def test_single_coach_full_period_gets_full_pool():
    coach = make_coach()
    student = make_student()
    start = date(2024, 1, 1)
    end   = date(2024, 1, 31)  # 30 days
    make_interval(coach, student, start, end)

    splits = compute_split(student.pk, start, end, 250_000)

    assert len(splits) == 1
    assert splits[0]['coach_id'] == coach.pk
    assert splits[0]['days'] == 30
    assert splits[0]['amount_kurus'] == 250_000


@pytest.mark.django_db
def test_worked_example_10_20_days():
    """pool 250000 with coach A 10 days then coach B 20 days -> A 83333, B 166667"""
    coach_a = make_coach()
    coach_b = make_coach()
    student = make_student()

    start = date(2024, 1, 1)
    mid   = date(2024, 1, 11)
    end   = date(2024, 1, 31)  # period = 30 days

    make_interval(coach_a, student, start, mid)   # 10 days
    make_interval(coach_b, student, mid, end)     # 20 days

    splits = compute_split(student.pk, start, end, 250_000)

    by_coach = {s['coach_id']: s for s in splits}
    assert by_coach[coach_a.pk]['days'] == 10
    assert by_coach[coach_b.pk]['days'] == 20
    assert by_coach[coach_a.pk]['amount_kurus'] == 83_333
    assert by_coach[coach_b.pk]['amount_kurus'] == 166_667
    assert sum(s['amount_kurus'] for s in splits) == 250_000


@pytest.mark.django_db
def test_worked_example_7_8_15_days():
    """pool 250000, 30-day period, 3 coaches 7+8+15 -> remainder to last"""
    coach_a = make_coach()
    coach_b = make_coach()
    coach_c = make_coach()
    student = make_student()

    d0 = date(2024, 1, 1)
    d1 = date(2024, 1, 8)   # +7
    d2 = date(2024, 1, 16)  # +8
    d3 = date(2024, 1, 31)  # +15

    make_interval(coach_a, student, d0, d1)
    make_interval(coach_b, student, d1, d2)
    make_interval(coach_c, student, d2, d3)

    splits = compute_split(student.pk, d0, d3, 250_000)

    by_coach = {s['coach_id']: s for s in splits}
    assert by_coach[coach_a.pk]['amount_kurus'] == 58_333   # floor(250000*7/30)
    assert by_coach[coach_b.pk]['amount_kurus'] == 66_666   # floor(250000*8/30)
    assert by_coach[coach_c.pk]['amount_kurus'] == 125_001  # floor + remainder
    assert sum(s['amount_kurus'] for s in splits) == 250_000


@pytest.mark.django_db
def test_gap_case_uncoached_days_paid_to_nobody():
    """25 coached days out of 30 -> 5 gap days are lost, no remainder rule applies."""
    coach = make_coach()
    student = make_student()

    start = date(2024, 1, 1)
    end   = date(2024, 1, 31)  # 30 days
    coach_end = date(2024, 1, 26)  # only 25 days covered

    make_interval(coach, student, start, coach_end)

    splits = compute_split(student.pk, start, end, 250_000)

    assert len(splits) == 1
    assert splits[0]['coach_id'] == coach.pk
    assert splits[0]['days'] == 25
    # floor(250000 * 25 / 30) = 208333; no remainder since gap exists
    assert splits[0]['amount_kurus'] == 208_333
    # Total < pool — gap days go nowhere
    assert splits[0]['amount_kurus'] < 250_000


@pytest.mark.django_db
def test_no_interval_logs_falls_back_to_current_coach():
    """Entire period is a gap -> 100% to current active coach, gap_fallback=True."""
    coach = make_coach()
    student = make_student()
    baker.make(CoachStudent, coach=coach, student=student, active=True, source='vagus')

    start = date(2024, 1, 1)
    end   = date(2024, 1, 31)

    splits = compute_split(student.pk, start, end, 250_000)

    assert len(splits) == 1
    assert splits[0]['coach_id'] == coach.pk
    assert splits[0]['amount_kurus'] == 250_000
    assert splits[0]['gap_fallback'] is True


@pytest.mark.django_db
def test_no_interval_no_active_coach_returns_empty():
    student = make_student()
    splits = compute_split(student.pk, date(2024, 1, 1), date(2024, 1, 31), 250_000)
    assert splits == []


@pytest.mark.django_db
def test_zero_pool_returns_empty():
    student = make_student()
    splits = compute_split(student.pk, date(2024, 1, 1), date(2024, 1, 31), 0)
    assert splits == []

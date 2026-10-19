"""
Tests for the earnings_preview management command.
Verifies printed split lines, totals, and Vagus remainder — no DB writes.
"""
import uuid
from datetime import date, datetime, time
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils.timezone import make_aware
from model_bakery import baker

from earnings_app.models import EarningRow
from purchase_app.models import Order, Plan
from users_app.models import CoachStudent, CoachStudentInterval, User


def make_coach(**kw):
    return baker.make(User, role='coach', is_active=True, is_approved=True, **kw)


def make_student(**kw):
    return baker.make(User, role='student', is_active=True, **kw)


def make_interval(coach, student, start_date, end_date=None):
    started_at = make_aware(datetime.combine(start_date, time.min))
    ended_at   = make_aware(datetime.combine(end_date, time.min)) if end_date else None
    return baker.make(
        CoachStudentInterval,
        coach=coach, student=student, source='vagus',
        started_at=started_at, ended_at=ended_at,
    )


def run_preview(*args, **kwargs):
    out = StringIO()
    call_command('earnings_preview', *args, stdout=out, **kwargs)
    return out.getvalue()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_plan(coach_share=250_000, duration=30):
    return baker.make(
        Plan, duration_days=duration, active=True,
        price_kurus=319_900, coach_share_kurus=coach_share,
    )


def make_paid_order(coach, student, plan):
    return baker.make(
        Order,
        email=student.email,
        full_name=student.full_name,
        coach=coach, plan=plan,
        amount_kurus=plan.price_kurus,
        status=Order.STATUS_PAID,
        student=student,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
    )


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_single_coach_full_period():
    """Single coach, full 30-day period → full pool."""
    coach   = make_coach(full_name='Ali Koç')
    student = make_student()
    plan    = make_plan(coach_share=250_000)
    order   = make_paid_order(coach, student, plan)

    start = date(2024, 1, 1)
    end   = date(2024, 1, 31)

    baker.make(
        EarningRow,
        order=order, coach=coach, student=student,
        coverage_start=start, coverage_end=end,
        period_days=30, coach_days=0,
        pool_kurus=250_000, amount_kurus=0,
        status=EarningRow.STATUS_HELD,
    )
    make_interval(coach, student, start, end)

    output = run_preview(order.pk)

    assert f'#{order.pk}' in output
    assert '2024-01-01' in output
    assert '2024-01-31' in output
    assert '2500' in output          # pool in TL
    assert 'Ali Koç' in output
    assert '30' in output            # days
    # full pool → 250000 kr → 2500 TL; Vagus leftover = 0
    assert "Vagus'ta kalan: 0 TL" in output


@pytest.mark.django_db
def test_two_coach_split_10_20():
    """10+20 day split: coach A 83300 kr (833 TL), coach B 166600 kr (1666 TL)."""
    coach_a = make_coach(full_name='Coach A')
    coach_b = make_coach(full_name='Coach B')
    student = make_student()
    plan    = make_plan(coach_share=250_000)
    order   = make_paid_order(coach_a, student, plan)

    start = date(2024, 1, 1)
    mid   = date(2024, 1, 11)
    end   = date(2024, 1, 31)

    baker.make(
        EarningRow,
        order=order, coach=coach_a, student=student,
        coverage_start=start, coverage_end=end,
        period_days=30, coach_days=0,
        pool_kurus=250_000, amount_kurus=0,
        status=EarningRow.STATUS_HELD,
    )
    make_interval(coach_a, student, start, mid)
    make_interval(coach_b, student, mid, end)

    output = run_preview(order.pk)

    assert 'Coach A' in output
    assert 'Coach B' in output
    assert '833' in output      # 83300 kr → 833 TL
    assert '1666' in output     # 166600 kr → 1666 TL
    # 83300 + 166600 = 249900; leftover = 100 kr = 1 TL
    assert "Vagus'ta kalan: 1 TL" in output


@pytest.mark.django_db
def test_as_of_overrides_coverage_end():
    """--as-of truncates the coverage window used for the split."""
    coach   = make_coach(full_name='Solo Coach')
    student = make_student()
    plan    = make_plan(coach_share=250_000)
    order   = make_paid_order(coach, student, plan)

    start = date(2024, 1, 1)
    end   = date(2024, 1, 31)

    baker.make(
        EarningRow,
        order=order, coach=coach, student=student,
        coverage_start=start, coverage_end=end,
        period_days=30, coach_days=0,
        pool_kurus=250_000, amount_kurus=0,
        status=EarningRow.STATUS_HELD,
    )
    make_interval(coach, student, start, end)

    # Release as-of day 10: only 10 days covered
    output = run_preview(order.pk, as_of='2024-01-11')

    assert '--as-of' in output
    assert '2024-01-11' in output
    # floor(250000*10/10) = 250000 → full pool (single coach covers all 10 days)
    assert '2500' in output


@pytest.mark.django_db
def test_no_coach_found_prints_warning():
    """No intervals and no active CoachStudent → prints warning, no split."""
    coach   = make_coach()
    student = make_student()
    plan    = make_plan(coach_share=250_000)
    order   = make_paid_order(coach, student, plan)

    baker.make(
        EarningRow,
        order=order, coach=coach, student=student,
        coverage_start=date(2024, 1, 1), coverage_end=date(2024, 1, 31),
        period_days=30, coach_days=0,
        pool_kurus=250_000, amount_kurus=0,
        status=EarningRow.STATUS_HELD,
    )
    # No intervals, no active CoachStudent link

    output = run_preview(order.pk)

    assert 'bulunamadı' in output.lower() or 'Koç bulunamadı' in output


@pytest.mark.django_db
def test_invalid_order_raises():
    with pytest.raises(CommandError):
        run_preview(999999)


@pytest.mark.django_db
def test_invalid_date_raises():
    coach   = make_coach()
    student = make_student()
    plan    = make_plan()
    order   = make_paid_order(coach, student, plan)

    with pytest.raises(CommandError):
        run_preview(order.pk, as_of='not-a-date')


@pytest.mark.django_db
def test_no_student_prints_warning():
    """Order without a student → prints 'Öğrenci atanmamış'."""
    coach = make_coach()
    plan  = make_plan()
    order = baker.make(
        Order,
        email='anon@example.com', full_name='Anon',
        coach=coach, plan=plan,
        amount_kurus=plan.price_kurus,
        status=Order.STATUS_PAID,
        student=None,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
    )
    baker.make(
        EarningRow,
        order=order, coach=coach, student=coach,  # dummy student fk bypass
        coverage_start=date(2024, 1, 1), coverage_end=date(2024, 1, 31),
        period_days=30, coach_days=0,
        pool_kurus=250_000, amount_kurus=0,
        status=EarningRow.STATUS_HELD,
    )

    output = run_preview(order.pk)
    assert 'atanmamış' in output

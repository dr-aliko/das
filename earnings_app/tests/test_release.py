"""
Tests for release_held_earnings:
- single coach full period release
- multi-coach split on release
- remainder rule applied at release
- gap fallback at release
- idempotency (running twice)
- refund voids held earnings
- manual record release
- renewal coverage_start logic
"""
import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from model_bakery import baker

from earnings_app.models import EarningRow, ManualPaymentRecord
from earnings_app.services import (
    create_earning_for_manual_record,
    create_holding_earning,
    release_held_earnings,
    void_order_earnings,
)
from purchase_app.models import Order, Plan
from purchase_app.services import on_payment_success
from users_app.models import CoachStudent, CoachStudentInterval, User


def make_coach(**kw):
    return baker.make(User, role='coach', is_active=True, is_approved=True, **kw)


def make_student(**kw):
    return baker.make(User, role='student', is_active=True, **kw)


def make_interval(coach, student, start_date, end_date=None):
    from datetime import datetime, time
    from django.utils.timezone import make_aware
    started_at = make_aware(datetime.combine(start_date, time.min))
    ended_at = make_aware(datetime.combine(end_date, time.min)) if end_date else None
    return baker.make(
        CoachStudentInterval,
        coach=coach, student=student, source='vagus',
        started_at=started_at, ended_at=ended_at,
    )


def make_paid_plan(coach_share=250_000, duration=30, **kw):
    return baker.make(
        Plan, duration_days=duration, active=True,
        price_kurus=319_900, coach_share_kurus=coach_share, **kw
    )


def make_paid_order(coach, student, plan, **kw):
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
        **kw,
    )


@pytest.mark.django_db
def test_single_coach_full_period_release():
    coach = make_coach()
    student = make_student()
    plan = make_paid_plan()
    order = make_paid_order(coach, student, plan)

    start = date(2024, 1, 1)
    end   = date(2024, 1, 31)
    make_interval(coach, student, start, end)

    row = baker.make(
        EarningRow,
        order=order, coach=coach, student=student,
        coverage_start=start, coverage_end=end,
        period_days=30, coach_days=0,
        pool_kurus=250_000, amount_kurus=0,
        status=EarningRow.STATUS_HELD,
    )

    released = release_held_earnings(today=end)

    assert released == 1
    row.refresh_from_db()
    assert row.status == EarningRow.STATUS_RELEASED
    assert row.amount_kurus == 250_000
    assert row.coach_days == 30


@pytest.mark.django_db
def test_multi_coach_split_on_release():
    coach_a = make_coach()
    coach_b = make_coach()
    student = make_student()
    plan = make_paid_plan()
    order = make_paid_order(coach_a, student, plan)

    start = date(2024, 1, 1)
    mid   = date(2024, 1, 11)
    end   = date(2024, 1, 31)

    make_interval(coach_a, student, start, mid)
    make_interval(coach_b, student, mid, end)

    baker.make(
        EarningRow,
        order=order, coach=coach_a, student=student,
        coverage_start=start, coverage_end=end,
        period_days=30, coach_days=0,
        pool_kurus=250_000, amount_kurus=0,
        status=EarningRow.STATUS_HELD,
    )

    release_held_earnings(today=end)

    rows = EarningRow.objects.filter(order=order).order_by('coach_days')
    assert rows.count() == 2
    by_coach = {r.coach_id: r for r in rows}
    assert by_coach[coach_a.pk].amount_kurus == 83_333
    assert by_coach[coach_b.pk].amount_kurus == 166_667
    assert all(r.status == EarningRow.STATUS_RELEASED for r in rows)


@pytest.mark.django_db
def test_release_idempotency():
    coach = make_coach()
    student = make_student()
    plan = make_paid_plan()
    order = make_paid_order(coach, student, plan)

    start = date(2024, 1, 1)
    end   = date(2024, 1, 31)
    make_interval(coach, student, start, end)

    baker.make(
        EarningRow,
        order=order, coach=coach, student=student,
        coverage_start=start, coverage_end=end,
        period_days=30, coach_days=0,
        pool_kurus=250_000, amount_kurus=0,
        status=EarningRow.STATUS_HELD,
    )

    release_held_earnings(today=end)
    count_after_first = EarningRow.objects.filter(order=order).count()
    release_held_earnings(today=end)
    count_after_second = EarningRow.objects.filter(order=order).count()

    assert count_after_first == count_after_second == 1


@pytest.mark.django_db
def test_held_not_released_before_coverage_ends():
    coach = make_coach()
    student = make_student()
    plan = make_paid_plan()
    order = make_paid_order(coach, student, plan)

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

    # Pass yesterday as today (coverage not ended)
    released = release_held_earnings(today=date(2024, 1, 15))
    assert released == 0
    assert EarningRow.objects.filter(order=order, status=EarningRow.STATUS_HELD).count() == 1


@pytest.mark.django_db
def test_refund_voids_held_earnings():
    coach = make_coach()
    student = make_student()
    plan = make_paid_plan()
    order = make_paid_order(coach, student, plan)

    row = baker.make(
        EarningRow,
        order=order, coach=coach, student=student,
        coverage_start=date(2024, 1, 1),
        coverage_end=date(2024, 1, 31),
        period_days=30, coach_days=0,
        pool_kurus=250_000, amount_kurus=0,
        status=EarningRow.STATUS_HELD,
    )

    void_order_earnings(order.pk, reason='order_refunded')

    row.refresh_from_db()
    assert row.status == EarningRow.STATUS_VOID
    assert row.void_reason == 'order_refunded'


@pytest.mark.django_db
def test_void_does_not_touch_paid_rows():
    coach = make_coach()
    student = make_student()
    plan = make_paid_plan()
    order = make_paid_order(coach, student, plan)

    paid_row = baker.make(
        EarningRow,
        order=order, coach=coach, student=student,
        coverage_start=date(2024, 1, 1),
        coverage_end=date(2024, 1, 31),
        period_days=30, coach_days=30,
        pool_kurus=250_000, amount_kurus=250_000,
        status=EarningRow.STATUS_PAID,
    )

    void_order_earnings(order.pk, reason='order_refunded')

    paid_row.refresh_from_db()
    assert paid_row.status == EarningRow.STATUS_PAID


@pytest.mark.django_db
def test_manual_record_creates_held_row():
    coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_staff=True, is_active=True)

    record = baker.make(
        ManualPaymentRecord,
        student=student, coach=coach,
        amount_kurus=319_900, coach_pool_kurus=250_000,
        date=date(2024, 1, 1), days=30,
        created_by=staff,
    )

    create_earning_for_manual_record(record)

    row = EarningRow.objects.get(manual_record=record)
    assert row.status == EarningRow.STATUS_HELD
    assert row.coverage_start == date(2024, 1, 1)
    assert row.coverage_end == date(2024, 1, 31)
    assert row.pool_kurus == 250_000


@pytest.mark.django_db
def test_manual_record_release_idempotent():
    coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_staff=True, is_active=True)

    start = date(2024, 1, 1)
    end   = date(2024, 1, 31)
    make_interval(coach, student, start, end)
    baker.make(CoachStudent, coach=coach, student=student, active=True, source='vagus')

    record = baker.make(
        ManualPaymentRecord,
        student=student, coach=coach,
        amount_kurus=319_900, coach_pool_kurus=250_000,
        date=start, days=30,
        created_by=staff,
    )
    create_earning_for_manual_record(record)
    create_earning_for_manual_record(record)  # should be no-op

    assert EarningRow.objects.filter(manual_record=record).count() == 1


@pytest.mark.django_db
def test_renewal_coverage_start_uses_previous_end():
    """Second order coverage_start = first order coverage_end."""
    coach = make_coach()
    student = make_student(email='renew@example.com')
    plan = make_paid_plan(duration=30)
    order1 = make_paid_order(coach, student, plan)

    create_holding_earning(order1)

    row1 = EarningRow.objects.get(order=order1)
    expected_start_for_order2 = row1.coverage_end

    order2 = make_paid_order(coach, student, plan)
    create_holding_earning(order2)

    row2 = EarningRow.objects.get(order=order2)
    assert row2.coverage_start == expected_start_for_order2


@pytest.mark.django_db
def test_gap_fallback_tagged_on_release():
    coach = make_coach()
    student = make_student()
    plan = make_paid_plan()
    order = make_paid_order(coach, student, plan)

    # No interval log — triggers gap fallback
    baker.make(CoachStudent, coach=coach, student=student, active=True, source='vagus')

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

    release_held_earnings(today=end)

    row = EarningRow.objects.get(order=order)
    assert row.gap_fallback is True
    assert row.amount_kurus == 250_000

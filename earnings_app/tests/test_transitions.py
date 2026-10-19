"""
Tests for approve/pay transitions and stamps, void paths, coach cannot approve.
"""
import pytest
from datetime import date

from model_bakery import baker

from earnings_app.models import EarningRow
from earnings_app.services import approve_earning, mark_paid, void_earning
from users_app.models import User


def make_coach(**kw):
    return baker.make(User, role='coach', is_active=True, is_approved=True, **kw)


def make_staff(**kw):
    return baker.make(User, role='coach', is_active=True, is_staff=True, **kw)


def make_student(**kw):
    return baker.make(User, role='student', is_active=True, **kw)


def make_row(coach, student, status=EarningRow.STATUS_RELEASED, **kw):
    return baker.make(
        EarningRow,
        coach=coach, student=student,
        coverage_start=date(2024, 1, 1),
        coverage_end=date(2024, 1, 31),
        period_days=30, coach_days=30,
        pool_kurus=250_000, amount_kurus=250_000,
        status=status, **kw,
    )


@pytest.mark.django_db
def test_approve_transitions_status_and_stamps_actor():
    staff = make_staff()
    coach = make_coach()
    student = make_student()
    row = make_row(coach, student, status=EarningRow.STATUS_RELEASED)

    approve_earning(row, staff)

    row.refresh_from_db()
    assert row.status == EarningRow.STATUS_APPROVED
    assert row.approved_at is not None
    assert row.approved_by == staff


@pytest.mark.django_db
def test_mark_paid_transitions_status_and_stamps_ref():
    staff = make_staff()
    coach = make_coach()
    student = make_student()
    row = make_row(coach, student, status=EarningRow.STATUS_APPROVED)

    mark_paid(row, staff, payout_ref='REF-001')

    row.refresh_from_db()
    assert row.status == EarningRow.STATUS_PAID
    assert row.paid_at is not None
    assert row.paid_by == staff
    assert row.payout_ref == 'REF-001'


@pytest.mark.django_db
def test_paid_row_is_immutable_to_void():
    staff = make_staff()
    coach = make_coach()
    student = make_student()
    row = make_row(coach, student, status=EarningRow.STATUS_PAID)

    with pytest.raises(ValueError, match='iptal edilemez'):
        void_earning(row, staff)


@pytest.mark.django_db
def test_approve_requires_released_status():
    staff = make_staff()
    coach = make_coach()
    student = make_student()
    row = make_row(coach, student, status=EarningRow.STATUS_HELD)

    with pytest.raises(ValueError, match='serbest satırlar'):
        approve_earning(row, staff)


@pytest.mark.django_db
def test_mark_paid_requires_approved_status():
    staff = make_staff()
    coach = make_coach()
    student = make_student()
    row = make_row(coach, student, status=EarningRow.STATUS_RELEASED)

    with pytest.raises(ValueError, match='onaylanmış satırlar'):
        mark_paid(row, staff)


@pytest.mark.django_db
def test_void_held_row():
    staff = make_staff()
    coach = make_coach()
    student = make_student()
    row = make_row(coach, student, status=EarningRow.STATUS_HELD)

    void_earning(row, staff, reason='test_void')

    row.refresh_from_db()
    assert row.status == EarningRow.STATUS_VOID
    assert row.voided_at is not None
    assert row.voided_by == staff
    assert row.void_reason == 'test_void'


@pytest.mark.django_db
def test_void_released_row():
    staff = make_staff()
    coach = make_coach()
    student = make_student()
    row = make_row(coach, student, status=EarningRow.STATUS_RELEASED)

    void_earning(row, staff)

    row.refresh_from_db()
    assert row.status == EarningRow.STATUS_VOID


@pytest.mark.django_db
def test_void_approved_row():
    staff = make_staff()
    coach = make_coach()
    student = make_student()
    row = make_row(coach, student, status=EarningRow.STATUS_APPROVED)

    void_earning(row, staff)

    row.refresh_from_db()
    assert row.status == EarningRow.STATUS_VOID


@pytest.mark.django_db
def test_coach_cannot_approve_via_view(db):
    """Coach hitting the approve endpoint gets redirected (not staff)."""
    from django.test import Client
    from django.urls import reverse

    coach = make_coach()
    student = make_student()
    row = make_row(coach, student, status=EarningRow.STATUS_RELEASED)

    c = Client()
    c.force_login(coach)
    url = reverse('earnings_panel:approve', args=[row.pk])
    response = c.post(url)

    assert response.status_code in (302, 403)
    row.refresh_from_db()
    assert row.status == EarningRow.STATUS_RELEASED

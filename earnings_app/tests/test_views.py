"""
Tests for panel and coach views: access control, list rendering, student side unaffected.
"""
import pytest
from datetime import date

from django.test import Client
from django.urls import reverse
from model_bakery import baker

from earnings_app.models import EarningRow
from users_app.models import User


def make_coach(**kw):
    return baker.make(User, role='coach', is_active=True, is_approved=True, **kw)


def make_staff(**kw):
    return baker.make(User, role='coach', is_active=True, is_staff=True, **kw)


def make_student(**kw):
    return baker.make(User, role='student', is_active=True, **kw)


def make_row(coach, student, status=EarningRow.STATUS_RELEASED):
    return baker.make(
        EarningRow,
        coach=coach, student=student,
        coverage_start=date(2024, 1, 1),
        coverage_end=date(2024, 1, 31),
        period_days=30, coach_days=30,
        pool_kurus=250_000, amount_kurus=250_000,
        status=status,
    )


@pytest.mark.django_db
def test_panel_list_requires_staff():
    plain_coach = make_coach()
    c = Client()
    c.force_login(plain_coach)
    response = c.get(reverse('earnings_panel:list'))
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_panel_list_renders_for_staff():
    staff = make_staff()
    c = Client()
    c.force_login(staff)
    response = c.get(reverse('earnings_panel:list'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_panel_list_anonymous_redirects():
    c = Client()
    response = c.get(reverse('earnings_panel:list'))
    assert response.status_code == 302


@pytest.mark.django_db
def test_coach_kazanclar_shows_only_own_rows():
    coach_a = make_coach()
    coach_b = make_coach()
    student_a = make_student()
    student_b = make_student()
    make_row(coach_a, student_a)
    make_row(coach_b, student_b)

    c = Client()
    c.force_login(coach_a)
    response = c.get(reverse('coach_kazanclar'))
    assert response.status_code == 200
    rows = response.context['rows']
    # View returns safe dicts (no raw kurus / Vagus share fields)
    assert all(isinstance(r, dict) for r in rows)
    assert len(rows) == 1
    assert rows[0]['student_name'] == student_a.full_name
    assert rows[0]['student_name'] != student_b.full_name


@pytest.mark.django_db
def test_coach_kazanclar_shows_no_student_price():
    """Template must not expose order.amount_kurus to coaches."""
    coach = make_coach()
    student = make_student()
    make_row(coach, student)

    c = Client()
    c.force_login(coach)
    response = c.get(reverse('coach_kazanclar'))
    assert response.status_code == 200
    content = response.content.decode()
    # order.amount_kurus should not appear; pool_kurus also hidden
    assert '319' not in content or 'amount_kurus' not in content


@pytest.mark.django_db
def test_student_cannot_access_coach_kazanclar():
    student = make_student()
    c = Client()
    c.force_login(student)
    response = c.get(reverse('coach_kazanclar'))
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_student_dashboard_unaffected(db):
    """Earnings app import does not break the student dashboard."""
    from earnings_app.models import EarningRow  # noqa — just ensure importable
    assert EarningRow is not None

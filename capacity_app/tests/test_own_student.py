"""
Tests for the own-student / Vagus-student distinction:
- is_own_student_source helper (vagus / coach / NULL+paid / NULL+none)
- capacity in_use excludes Vagus-sourced students
- roster renders source tags and three source-filter counts
"""
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from capacity_app.models import CoachCapacityGrant
from capacity_app.services import get_capacity_status, is_own_student_source
from users_app.models import CoachStudent

User = get_user_model()


@pytest.fixture
def coach(db):
    u = baker.make(User, role='coach', is_active=True, is_approved=True)
    u.set_password('pw')
    u.save()
    return u


@pytest.fixture
def coach_client(coach):
    c = Client()
    c.login(username=coach.email, password='pw')
    return c


# ── Helper tests ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_is_own_student_source_all_cases():
    """is_own_student_source: vagus=False, coach=True, NULL+paid=False, NULL+none=True."""
    from purchase_app.models import Order
    student_with_order = baker.make(User, role='student', is_active=True)
    baker.make(Order, student=student_with_order, status=Order.STATUS_PAID)
    student_no_order = baker.make(User, role='student', is_active=True)

    assert is_own_student_source('vagus') is False
    assert is_own_student_source('coach') is True
    assert is_own_student_source(None, student_with_order) is False
    assert is_own_student_source(None, student_no_order) is True


# ── Capacity count ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_capacity_excludes_vagus(coach):
    """Vagus-sourced active links must not count toward capacity in_use."""
    today = date.today()
    baker.make(
        CoachCapacityGrant, coach=coach, slots=5,
        period_start=today, period_end=today + timedelta(days=30), order=None,
    )

    vagus_student = baker.make(User, role='student', is_active=True)
    baker.make(CoachStudent, coach=coach, student=vagus_student,
               source='vagus', active=True)

    own_student = baker.make(User, role='student', is_active=True)
    baker.make(CoachStudent, coach=coach, student=own_student,
               source='coach', active=True)

    status = get_capacity_status(coach)
    assert status['in_use'] == 1   # only own student counts
    assert status['granted'] == 5
    assert status['free'] == 4


# ── Roster source split ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_roster_source_split(coach, coach_client, settings):
    """
    Roster renders Vagus/Kendi tags on cards and shows three source-filter buttons
    with correct counts in context.
    """
    settings.COACH_CAPACITY_ENFORCED = False

    vagus_student = baker.make(
        User, role='student', is_active=True, full_name='Vagus Student', coach=coach,
    )
    baker.make(CoachStudent, coach=coach, student=vagus_student,
               source='vagus', active=True)

    own_student = baker.make(
        User, role='student', is_active=True, full_name='Own Student', coach=coach,
    )
    baker.make(CoachStudent, coach=coach, student=own_student,
               source='coach', active=True)

    resp = coach_client.get(reverse('coach:dashboard'))
    assert resp.status_code == 200

    assert resp.context['total_vagus'] == 1
    assert resp.context['total_own'] == 1

    body = resp.content.decode('utf-8')
    assert 'Vagus öğrencilerim' in body
    assert 'Kendi öğrencilerim' in body
    # Source tags on cards
    assert '>Vagus<' in body
    assert '>Kendi<' in body

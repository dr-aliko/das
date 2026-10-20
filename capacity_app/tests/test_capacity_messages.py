"""
Tests for capacity error message UX.

Covers:
- Coach invite page: error text has no URL, page has a button link to capacity page
- "Kontenjanınız yok." when no grants ever; "doldu" when grants exist but full
- Student invite page: shows neutral message, no capacity link
- COACH_CAPACITY_ENFORCED=False: invite succeeds, no error shown
"""
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from capacity_app.models import CoachCapacityGrant
from capacity_app.services import can_add_own_student

User = get_user_model()


@pytest.fixture
def coach(db):
    u = baker.make(User, role='coach', is_active=True, is_approved=True)
    u.set_password('testpass')
    u.save()
    return u


@pytest.fixture
def coach_client(coach):
    c = Client()
    c.login(username=coach.email, password='testpass')
    return c


@pytest.fixture
def pending_invite(db, coach):
    from users_app.models import StudentInvite
    return baker.make(
        StudentInvite,
        coach=coach,
        email='student@example.com',
        token=StudentInvite.generate_token(),
        is_used=False,
        initiated_by_staff=False,
    )


# ── Service: message text ──────────────────────────────────────────────────────

@pytest.mark.django_db
def test_no_grants_message_says_yok(coach, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    allowed, msg = can_add_own_student(coach)
    assert not allowed
    assert 'yok' in msg.lower()
    assert 'http' not in msg
    assert '/coach/kontenjan/' not in msg


@pytest.mark.django_db
def test_full_capacity_message_says_doldu(coach, settings, db):
    settings.COACH_CAPACITY_ENFORCED = True
    today = date.today()
    baker.make(
        CoachCapacityGrant,
        coach=coach, slots=1,
        period_start=today, period_end=today + timedelta(days=30),
        order=None,
    )
    from users_app.models import CoachStudent
    student = baker.make(User, role='student', is_active=True, is_approved=True)
    baker.make(CoachStudent, coach=coach, student=student, active=True, source='coach')

    allowed, msg = can_add_own_student(coach)
    assert not allowed
    assert 'doldu' in msg.lower()
    assert 'http' not in msg
    assert '/coach/kontenjan/' not in msg


# ── Coach invite page ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_coach_invite_page_error_has_no_url_text(coach, coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.post(reverse('users_app:coach_invites'), {
        'email': 'x@example.com', 'full_name': 'Test',
    })
    assert resp.status_code == 200
    ctx = resp.context['capacity_error']
    assert ctx  # error was set
    assert 'http' not in ctx
    assert '/coach/kontenjan/' not in ctx


@pytest.mark.django_db
def test_coach_invite_page_html_has_capacity_button(coach, coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.post(reverse('users_app:coach_invites'), {
        'email': 'x@example.com', 'full_name': 'Test',
    })
    assert resp.status_code == 200
    capacity_url = reverse('capacity:page')
    assert capacity_url.encode() in resp.content


# ── Student invite page ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_student_invite_page_neutral_message(coach, settings, pending_invite):
    settings.COACH_CAPACITY_ENFORCED = True
    c = Client()
    resp = c.post(f'/auth/invite/{pending_invite.token}/', {
        'full_name': 'Test Student',
        'password1': 'Testpass123!',
        'password2': 'Testpass123!',
        'terms_accepted': 'on',
        'kvkk_accepted': 'on',
    })
    assert resp.status_code == 200
    body = resp.content.decode('utf-8')
    assert 'koçunuzla iletişime' in body


@pytest.mark.django_db
def test_student_invite_page_no_capacity_link(coach, settings, pending_invite):
    settings.COACH_CAPACITY_ENFORCED = True
    c = Client()
    resp = c.post(f'/auth/invite/{pending_invite.token}/', {
        'full_name': 'Test Student',
        'password1': 'Testpass123!',
        'password2': 'Testpass123!',
        'terms_accepted': 'on',
        'kvkk_accepted': 'on',
    })
    body = resp.content.decode('utf-8')
    assert '/coach/kontenjan/' not in body
    capacity_url = reverse('capacity:page')
    assert capacity_url not in body


@pytest.mark.django_db
def test_student_invite_page_no_buy_wording(coach, settings, pending_invite):
    settings.COACH_CAPACITY_ENFORCED = True
    c = Client()
    resp = c.post(f'/auth/invite/{pending_invite.token}/', {
        'full_name': 'Test Student',
        'password1': 'Testpass123!',
        'password2': 'Testpass123!',
        'terms_accepted': 'on',
        'kvkk_accepted': 'on',
    })
    body = resp.content.decode('utf-8')
    assert 'satın al' not in body.lower()


# ── Flag off ───────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_flag_off_invite_succeeds(coach, coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = False
    from users_app.models import StudentInvite
    resp = coach_client.post(reverse('users_app:coach_invites'), {
        'email': 'flagoff@example.com', 'full_name': 'Flag Off',
    })
    assert resp.status_code == 302
    assert StudentInvite.objects.filter(email='flagoff@example.com').exists()


@pytest.mark.django_db
def test_flag_off_no_capacity_error_in_context(coach, coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = False
    resp = coach_client.post(reverse('users_app:coach_invites'), {
        'email': 'flagoff2@example.com', 'full_name': 'Flag Off 2',
    })
    assert resp.status_code == 302  # redirected on success, no error context

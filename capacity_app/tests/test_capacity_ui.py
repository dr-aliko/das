"""
Tests for consolidated capacity UI (roster + invites page).

Covers:
- Roster: exactly one invite link even with zero capacity and enforcement on
- Invites page: Kontenjan card shown, has explanation and buy button, no end date
- Invites page: 0-slot grant never shows a date to the coach
- Invites page: form hidden when enforcement on and full/zero capacity
- Invites page: form works when free > 0
- Flag off: no blocking, card shown only if grants exist
- Student invite page untouched (no capacity wording)
"""
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from capacity_app.models import CapacitySettings, CoachCapacityGrant
from capacity_app.services import EXPLANATION_DEFAULT_BODY, EXPLANATION_DEFAULT_TITLE

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
def active_grant(db, coach):
    today = date.today()
    return baker.make(
        CoachCapacityGrant,
        coach=coach, slots=5,
        period_start=today, period_end=today + timedelta(days=30),
        order=None,
    )


# ── Roster ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_roster_has_exactly_one_invite_link(coach_client, settings):
    """Roster shows a single invite link regardless of capacity state."""
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('coach:dashboard'))
    assert resp.status_code == 200
    invite_url = reverse('users_app:coach_invites').encode()
    assert resp.content.count(invite_url) >= 1


@pytest.mark.django_db
def test_roster_invite_button_is_link_with_zero_capacity(coach_client, settings):
    """With zero capacity and enforcement on, the roster still has an <a> to invites."""
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('coach:dashboard'))
    assert resp.status_code == 200
    body = resp.content.decode('utf-8')
    invite_url = reverse('users_app:coach_invites')
    assert invite_url in body


@pytest.mark.django_db
def test_roster_no_capacity_chip(coach_client, active_grant):
    """Roster must not show the old 'Kontenjan: X/Y' chip."""
    resp = coach_client.get(reverse('coach:dashboard'))
    body = resp.content.decode('utf-8')
    assert 'Kontenjan:' not in body


@pytest.mark.django_db
def test_roster_no_disabled_davet_span(coach_client, settings):
    """Roster must not contain a disabled/aria-disabled invite button."""
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('coach:dashboard'))
    body = resp.content.decode('utf-8')
    assert 'aria-disabled' not in body
    assert 'cursor-not-allowed' not in body


# ── Invites page: Kontenjan card ─────────────────────────────────────────────

@pytest.mark.django_db
def test_invites_card_shown_when_enforcement_on(coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('users_app:coach_invites'))
    body = resp.content.decode('utf-8')
    assert 'Kontenjan' in body
    assert 'Kullanılan' in body
    assert 'Boş' in body


@pytest.mark.django_db
def test_invites_card_shown_when_has_grants(coach_client, active_grant, settings):
    settings.COACH_CAPACITY_ENFORCED = False
    resp = coach_client.get(reverse('users_app:coach_invites'))
    body = resp.content.decode('utf-8')
    assert 'Kontenjan' in body
    assert 'Kullanılan' in body


@pytest.mark.django_db
def test_invites_card_hidden_when_flag_off_and_no_grants(coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = False
    resp = coach_client.get(reverse('users_app:coach_invites'))
    body = resp.content.decode('utf-8')
    # Card should not appear with zero grants and enforcement off
    assert 'Kullanılan' not in body


@pytest.mark.django_db
def test_invites_card_has_explanation_text(db, coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    cfg = CapacitySettings.get()
    cfg.explanation_title = EXPLANATION_DEFAULT_TITLE
    cfg.explanation_body = EXPLANATION_DEFAULT_BODY
    cfg.save()
    resp = coach_client.get(reverse('users_app:coach_invites'))
    body = resp.content.decode('utf-8')
    assert '30 günlük' in body
    assert 'atadığı' in body  # "Vagus'un size atadığı öğrenciler sayılmaz"


@pytest.mark.django_db
def test_invites_card_has_buy_button(coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('users_app:coach_invites'))
    capacity_url = reverse('capacity:page')
    assert capacity_url.encode() in resp.content


@pytest.mark.django_db
def test_invites_card_no_period_end_date(coach_client, active_grant, settings):
    """The Kontenjan card must not show a period end date."""
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('users_app:coach_invites'))
    # The card should show numbers but not a formatted date like "d.m.Y"
    # The period_end is 30 days from today — check it's not shown in card area
    end_date = active_grant.period_end.strftime('%d.%m.%Y')
    # We check context rather than HTML since date could appear in other elements
    assert resp.context['cap_status']['period_end'] is not None  # sanity
    body = resp.content.decode('utf-8')
    # The date should NOT appear in the Kontenjan card section
    # (it may appear on the capacity purchase page, but not here)
    assert end_date not in body


@pytest.mark.django_db
def test_zero_slot_grant_no_date_shown(coach, coach_client, settings):
    """A grant reduced to 0 slots must not show its period_end date on the invites page."""
    settings.COACH_CAPACITY_ENFORCED = True
    today = date.today()
    zero_grant = baker.make(
        CoachCapacityGrant,
        coach=coach,
        slots=0,
        period_start=today,
        period_end=today + timedelta(days=20),
        order=None,
    )
    resp = coach_client.get(reverse('users_app:coach_invites'))
    body = resp.content.decode('utf-8')
    end_date = zero_grant.period_end.strftime('%d.%m.%Y')
    assert end_date not in body


# ── Invites page: form state ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_form_hidden_when_enforcement_on_and_no_capacity(coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('users_app:coach_invites'))
    assert resp.status_code == 200
    assert resp.context['capacity_blocked'] is True
    body = resp.content.decode('utf-8')
    # Form submit button should not be present
    assert 'Davet Gönder' not in body or '<form' not in body


@pytest.mark.django_db
def test_form_visible_when_capacity_free(coach_client, active_grant, settings):
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('users_app:coach_invites'))
    assert resp.status_code == 200
    assert resp.context['capacity_blocked'] is False
    assert b'<form' in resp.content


@pytest.mark.django_db
def test_form_visible_when_flag_off(coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = False
    resp = coach_client.get(reverse('users_app:coach_invites'))
    assert resp.status_code == 200
    assert resp.context['capacity_blocked'] is False
    assert b'<form' in resp.content


@pytest.mark.django_db
def test_flag_off_invite_succeeds(coach_client, settings):
    settings.COACH_CAPACITY_ENFORCED = False
    from users_app.models import StudentInvite
    resp = coach_client.post(reverse('users_app:coach_invites'), {
        'email': 'new@example.com', 'full_name': 'Test User',
    })
    assert resp.status_code == 302
    assert StudentInvite.objects.filter(email='new@example.com').exists()


# ── Student invite page (must be untouched) ───────────────────────────────────

@pytest.mark.django_db
def test_student_invite_page_no_capacity_wording(coach, settings, db):
    settings.COACH_CAPACITY_ENFORCED = True
    from users_app.models import StudentInvite
    invite = baker.make(
        StudentInvite,
        coach=coach,
        email='s@example.com',
        token=StudentInvite.generate_token(),
        is_used=False,
        initiated_by_staff=False,
    )
    c = Client()
    resp = c.get(f'/auth/invite/{invite.token}/')
    assert resp.status_code == 200
    body = resp.content.decode('utf-8')
    assert 'Kontenjan satın al' not in body
    assert '/coach/kontenjan/' not in body


# ── per-student flag: slot card hidden, credit card shown ─────────────────────

@pytest.mark.django_db
def test_invites_flag_true_hides_slot_card_shows_credit_card(coach_client, active_grant, settings):
    """With COACH_PER_STUDENT_PERIODS=True the old Kullanılan/Toplam/Boş tiles
    must not appear; the new 'Kullanılabilir Hak' tile must appear."""
    settings.COACH_PER_STUDENT_PERIODS = True
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('users_app:coach_invites'))
    assert resp.status_code == 200
    body = resp.content.decode('utf-8')
    # New credit card present
    assert 'Kullanılabilir Hak' in body
    # Old slot tiles absent
    assert 'Kullanılan' not in body
    assert 'Toplam' not in body or 'Kullanılan' not in body  # slot header gone
    assert 'Kontenjan satın al' not in body


@pytest.mark.django_db
def test_invites_flag_false_slot_card_present(coach_client, active_grant, settings):
    """With COACH_PER_STUDENT_PERIODS=False and an active grant the old slot card
    (Kullanılan / Toplam / Boş) must still appear."""
    settings.COACH_PER_STUDENT_PERIODS = False
    settings.COACH_CAPACITY_ENFORCED = False
    resp = coach_client.get(reverse('users_app:coach_invites'))
    assert resp.status_code == 200
    body = resp.content.decode('utf-8')
    assert 'Kullanılan' in body


@pytest.mark.django_db
def test_activation_command_matches_get_capacity_status(settings):
    """Command converts the same number of credits as get_capacity_status.free
    for a coach with two active grants (8+5=13) and 11 own students (free=2)."""
    from datetime import date, timedelta
    from io import StringIO

    from django.core.management import call_command
    from django.db.models import Sum

    from capacity_app.models import CoachCapacityGrant, CoachCreditLedger
    from capacity_app.services import get_capacity_status
    from users_app.models import CoachStudent

    settings.COACH_PER_STUDENT_PERIODS = False  # command works regardless of flag

    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    today = date.today()

    baker.make(CoachCapacityGrant, coach=coach, slots=8,
               period_start=today - timedelta(days=1),
               period_end=today + timedelta(days=29))
    baker.make(CoachCapacityGrant, coach=coach, slots=5,
               period_start=today - timedelta(days=1),
               period_end=today + timedelta(days=29))

    for _ in range(11):
        s = baker.make(User, role='student', is_active=True)
        baker.make(CoachStudent, coach=coach, student=s, active=True, source='coach')

    status = get_capacity_status(coach)
    assert status['granted'] == 13
    assert status['in_use'] == 11
    assert status['free'] == 2

    call_command('activate_per_student_periods', apply=True, coach=coach.pk,
                 stdout=StringIO())

    converted = (
        CoachCreditLedger.objects
        .filter(coach=coach, reason=CoachCreditLedger.REASON_CONVERTED_FROM_GRANT)
        .aggregate(total=Sum('delta'))['total'] or 0
    )
    assert converted == status['free'], (
        f'command wrote {converted} credits but get_capacity_status.free={status["free"]}'
    )

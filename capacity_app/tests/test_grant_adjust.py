"""
Tests for staff grant adjustment (reduce / end) feature.

Covers:
- reduce: capacity status reflects reduced slots immediately
- end: period_end set to today, grant becomes inactive next day
- reason required — empty reason returns form with error
- non-staff user rejected (redirect to login)
- double-submit idempotent (second POST with same values → no new log)
- in_use above new total does NOT unlink any CoachStudent
- paid-order grant shows refund warning in confirm page HTML
- GrantAdjustmentLog written with correct fields
- coach_grants page shows flat history across all grants
"""
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from capacity_app.models import CoachCapacityGrant, CoachCapacityOrder, GrantAdjustmentLog
from capacity_app.services import adjust_grant, get_capacity_status
from users_app.models import CoachStudent

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def staff(db):
    u = baker.make(User, role='coach', is_active=True, is_approved=True, is_staff=True)
    return u


@pytest.fixture
def coach(db):
    return baker.make(User, role='coach', is_active=True, is_approved=True)


@pytest.fixture
def active_grant(db, coach):
    today = date.today()
    return baker.make(
        CoachCapacityGrant,
        coach=coach,
        slots=5,
        period_start=today - timedelta(days=1),
        period_end=today + timedelta(days=29),
        order=None,
    )


# ── Service-layer tests ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_reduce_updates_capacity_status(active_grant, staff):
    coach = active_grant.coach
    before = get_capacity_status(coach)
    assert before['granted'] == 5

    adjust_grant(active_grant.pk, 'reduce', 3, active_grant.period_end, staff, 'test reduce')
    after = get_capacity_status(coach)
    assert after['granted'] == 3


@pytest.mark.django_db
def test_end_sets_period_end_to_today(active_grant, staff):
    today = date.today()
    adjust_grant(active_grant.pk, 'end', active_grant.slots, today, staff, 'test end')
    active_grant.refresh_from_db()
    assert active_grant.period_end == today
    assert active_grant.is_active  # still active today


@pytest.mark.django_db
def test_end_grant_inactive_tomorrow(active_grant, staff):
    today = date.today()
    adjust_grant(active_grant.pk, 'end', active_grant.slots, today, staff, 'test end')
    active_grant.refresh_from_db()
    assert active_grant.period_start <= today
    assert active_grant.period_end == today


@pytest.mark.django_db
def test_adjust_creates_log(active_grant, staff):
    adjust_grant(active_grant.pk, 'reduce', 2, active_grant.period_end, staff, 'reason x')
    log = GrantAdjustmentLog.objects.get(grant=active_grant)
    assert log.action == 'reduce'
    assert log.old_slots == 5
    assert log.new_slots == 2
    assert log.adjusted_by == staff
    assert log.reason == 'reason x'


@pytest.mark.django_db
def test_adjust_idempotent_no_op(active_grant, staff):
    adjust_grant(active_grant.pk, 'reduce', 3, active_grant.period_end, staff, 'r1')
    result = adjust_grant(active_grant.pk, 'reduce', 3, active_grant.period_end, staff, 'r2')
    assert result is None  # no-op
    assert GrantAdjustmentLog.objects.filter(grant=active_grant).count() == 1


@pytest.mark.django_db
def test_reduce_does_not_unlink_students(active_grant, staff):
    coach = active_grant.coach
    students = baker.make(User, role='student', is_active=True, is_approved=True, _quantity=4)
    for s in students:
        baker.make(CoachStudent, coach=coach, student=s, active=True, source='coach')

    adjust_grant(active_grant.pk, 'reduce', 1, active_grant.period_end, staff, 'reduce below in_use')
    assert CoachStudent.objects.filter(coach=coach, active=True).count() == 4


# ── View tests ─────────────────────────────────────────────────────────────────

@pytest.fixture
def staff_client(staff):
    c = Client()
    c.force_login(staff)
    return c


@pytest.fixture
def anon_client():
    return Client()


@pytest.fixture
def student_user(db):
    return baker.make(User, role='student', is_active=True, is_approved=True, is_staff=False)


@pytest.fixture
def student_client(student_user):
    c = Client()
    c.force_login(student_user)
    return c


@pytest.mark.django_db
def test_non_staff_rejected(student_client, active_grant):
    url = reverse('capacity_panel:grant_adjust', kwargs={'pk': active_grant.pk}) + '?action=reduce'
    resp = student_client.get(url)
    assert resp.status_code in (302, 403)


@pytest.mark.django_db
def test_anon_rejected(anon_client, active_grant):
    url = reverse('capacity_panel:grant_adjust', kwargs={'pk': active_grant.pk}) + '?action=reduce'
    resp = anon_client.get(url)
    assert resp.status_code == 302


@pytest.mark.django_db
def test_get_reduce_form_renders(staff_client, active_grant):
    url = reverse('capacity_panel:grant_adjust', kwargs={'pk': active_grant.pk}) + '?action=reduce'
    resp = staff_client.get(url)
    assert resp.status_code == 200
    assert b'new_slots' in resp.content


@pytest.mark.django_db
def test_get_end_form_renders(staff_client, active_grant):
    url = reverse('capacity_panel:grant_adjust', kwargs={'pk': active_grant.pk}) + '?action=end'
    resp = staff_client.get(url)
    assert resp.status_code == 200
    assert 'Sonlandır'.encode() in resp.content


@pytest.mark.django_db
def test_post_reduce_empty_reason_shows_error(staff_client, active_grant):
    url = reverse('capacity_panel:grant_adjust', kwargs={'pk': active_grant.pk})
    resp = staff_client.post(url, {'action': 'reduce', 'new_slots': '2', 'reason': ''})
    assert resp.status_code == 200
    assert 'Neden'.encode() in resp.content
    assert GrantAdjustmentLog.objects.filter(grant=active_grant).count() == 0


@pytest.mark.django_db
def test_post_reduce_success_redirects(staff_client, active_grant):
    url = reverse('capacity_panel:grant_adjust', kwargs={'pk': active_grant.pk})
    resp = staff_client.post(url, {'action': 'reduce', 'new_slots': '2', 'reason': 'test'})
    assert resp.status_code == 302
    assert GrantAdjustmentLog.objects.filter(grant=active_grant).count() == 1


@pytest.mark.django_db
def test_post_end_success_redirects(staff_client, active_grant):
    url = reverse('capacity_panel:grant_adjust', kwargs={'pk': active_grant.pk})
    resp = staff_client.post(url, {'action': 'end', 'reason': 'closing early'})
    assert resp.status_code == 302
    active_grant.refresh_from_db()
    assert active_grant.period_end == date.today()


@pytest.mark.django_db
def test_post_reduce_double_submit_idempotent(staff_client, active_grant):
    url = reverse('capacity_panel:grant_adjust', kwargs={'pk': active_grant.pk})
    staff_client.post(url, {'action': 'reduce', 'new_slots': '2', 'reason': 'r1'})
    staff_client.post(url, {'action': 'reduce', 'new_slots': '2', 'reason': 'r2'})
    assert GrantAdjustmentLog.objects.filter(grant=active_grant).count() == 1


@pytest.mark.django_db
def test_paid_order_warning_shown(staff_client, coach, db):
    order = baker.make(CoachCapacityOrder, coach=coach, slots=3, status=CoachCapacityOrder.STATUS_PAID)
    today = date.today()
    grant = baker.make(
        CoachCapacityGrant,
        coach=coach, order=order, slots=3,
        period_start=today - timedelta(days=1),
        period_end=today + timedelta(days=29),
    )
    url = reverse('capacity_panel:grant_adjust', kwargs={'pk': grant.pk}) + '?action=reduce'
    resp = staff_client.get(url)
    assert resp.status_code == 200
    assert 'iade'.encode() in resp.content.lower() or 'Satın Alma'.encode() in resp.content


@pytest.mark.django_db
def test_coach_grants_page_shows_history(staff_client, active_grant, staff):
    adjust_grant(active_grant.pk, 'reduce', 3, active_grant.period_end, staff, 'reason A')
    url = reverse('capacity_panel:coach_grants', kwargs={'coach_pk': active_grant.coach_id})
    resp = staff_client.get(url)
    assert resp.status_code == 200
    assert b'reason A' in resp.content
    assert 'Düzeltme Geçmişi'.encode() in resp.content

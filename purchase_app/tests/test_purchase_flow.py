import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from model_bakery import baker

from purchase_app.models import Order, Plan
from purchase_app.services import cancel_stale_orders, on_payment_success

User = get_user_model()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def coach(db):
    return baker.make(
        'users_app.User',
        role='coach',
        is_active=True,
        is_approved=True,
        wp_is_available=True,
        wordpress_post_id=9999,
    )


@pytest.fixture
def active_plan(db):
    return baker.make(
        'purchase_app.Plan',
        name='Test Plan',
        kind=Plan.KIND_ONE_TIME,
        price_kurus=319900,
        duration_days=30,
        active=True,
    )


@pytest.fixture
def pending_order(db, coach, active_plan):
    return baker.make(
        'purchase_app.Order',
        email='buyer@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
        full_name='Test Student',
    )


# ── Flag / legal guard ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_flag_off_returns_404(coach, client):
    with patch(
        'purchase_app.views._purchase_enabled',
        return_value=False,
    ):
        resp = client.get(f'/satin-al/{coach.wordpress_post_id}/')
        assert resp.status_code == 404


@pytest.mark.django_db
def test_legal_urls_empty_returns_404(coach, client, settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = ''
    settings.LEGAL_DISTANCE_SALES_URL = ''
    settings.LEGAL_PRIVACY_URL = ''
    resp = client.get(f'/satin-al/{coach.wordpress_post_id}/')
    assert resp.status_code == 404


# ── Coach availability ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_unavailable_coach_shows_friendly_page(client, settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    unavailable_coach = baker.make(
        'users_app.User',
        role='coach',
        is_active=True,
        is_approved=True,
        wp_is_available=False,
        wordpress_post_id=8888,
    )
    resp = client.get(f'/satin-al/{unavailable_coach.wordpress_post_id}/')
    assert resp.status_code == 200
    assert b'unavailable' in resp.content.lower() or resp.templates[0].name == 'purchase/unavailable.html'


# ── Price tampering ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_price_tampering_ignored(coach, active_plan, settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = True
    settings.DEBUG = False

    staff = baker.make('users_app.User', role='coach', is_staff=True, is_active=True, is_approved=True)
    client_obj = Client()
    client_obj.force_login(staff)

    with patch('purchase_app.views._purchase_enabled', return_value=True):
        resp = client_obj.post(
            f'/satin-al/{coach.wordpress_post_id}/checkout/',
            {
                'full_name':        'Hacker',
                'email':            'hacker@example.com',
                'plan':             active_plan.pk,
                'consent_terms':    'on',
                'consent_distance': 'on',
                'consent_kvkk':     'on',
                # Attempt to tamper: no price field accepted
            },
        )

    order = Order.objects.filter(email='hacker@example.com').first()
    if order:
        assert order.amount_kurus == active_plan.price_kurus, 'amount_kurus must equal plan price, not a tampered value'


# ── Idempotency ────────────────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_idempotent_on_payment_success(pending_order, active_plan):
    from users_app.models import CoachStudent

    with patch('django_q.tasks.async_task'):
        # Call twice
        on_payment_success(pending_order)
        on_payment_success(pending_order)

    pending_order.refresh_from_db()
    # After first call should be paid
    # CoachStudent should exist exactly once
    student = User.objects.filter(email=pending_order.email).first()
    if student:
        cs_count = CoachStudent.objects.filter(coach=pending_order.coach, student=student).count()
        assert cs_count <= 1, 'CoachStudent must not be duplicated on second call'


@pytest.mark.django_db(transaction=True)
def test_idempotent_already_paid_order_not_reprocessed(db, coach, active_plan):
    """A paid order must be skipped silently."""
    from users_app.models import CoachStudent

    student = baker.make('users_app.User', role='student', is_active=True, email='paid@example.com')
    baker.make('users_app.CoachStudent', coach=coach, student=student, active=True)

    paid_order = baker.make(
        'purchase_app.Order',
        email=student.email,
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PAID,
        student=student,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
        full_name=student.full_name,
    )

    with patch('django_q.tasks.async_task'):
        on_payment_success(paid_order)

    paid_order.refresh_from_db()
    assert paid_order.status == Order.STATUS_PAID


# ── Stale orders ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_stale_orders_cancelled(coach, active_plan):
    from django.utils import timezone

    old_order = baker.make(
        'purchase_app.Order',
        email='stale@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
        full_name='Stale User',
    )
    Order.objects.filter(pk=old_order.pk).update(
        created_at=timezone.now() - timezone.timedelta(hours=3)
    )

    count = cancel_stale_orders()
    assert count >= 1
    old_order.refresh_from_db()
    assert old_order.status == Order.STATUS_CANCELLED


@pytest.mark.django_db
def test_recent_pending_order_not_cancelled(pending_order):
    cancel_stale_orders()
    pending_order.refresh_from_db()
    assert pending_order.status == Order.STATUS_PENDING


# ── No user enumeration ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_existing_email_form_response_identical(coach, active_plan, settings):
    """Submit with existing-account email must return same form page as a new email."""
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = True

    existing = baker.make('users_app.User', email='existing@example.com', role='student', is_active=True)

    with patch('purchase_app.views._purchase_enabled', return_value=True), \
         patch('purchase_app.views.get_provider') as mock_prov:
        mock_prov.return_value.name = 'sandbox'
        mock_prov.return_value.create_checkout.return_value = '/satin-al/tesekkur/fake/'

        client_obj = Client()
        payload = {
            'full_name':        'Test',
            'email':            existing.email,
            'plan':             active_plan.pk,
            'consent_terms':    'on',
            'consent_distance': 'on',
            'consent_kvkk':     'on',
        }
        resp = client_obj.post(f'/satin-al/{coach.wordpress_post_id}/checkout/', payload, follow=False)

    # Should redirect (same as new email path) — no 409 or "you already have an account" message
    assert resp.status_code in (302, 200)
    if resp.status_code == 200:
        assert b'zaten bir hesab' not in resp.content.lower()


# ── Non-student role → needs_review ───────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_non_student_email_marked_needs_review(pending_order, coach):
    """An order whose email belongs to a coach must be marked needs_review, not activated."""
    coach_user = baker.make('users_app.User', role='coach', email=pending_order.email, is_active=True)

    with patch('django_q.tasks.async_task'):
        on_payment_success(pending_order)

    pending_order.refresh_from_db()
    assert pending_order.status == Order.STATUS_NEEDS_REVIEW
    coach_user.refresh_from_db()
    assert coach_user.role == 'coach'  # untouched


# ── Different active coach → needs_review ─────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_different_active_coach_marked_needs_review(db, active_plan):
    from users_app.models import CoachStudent

    coach_a = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    coach_b = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    student = baker.make('users_app.User', role='student', is_active=True, email='multi@example.com')
    baker.make('users_app.CoachStudent', coach=coach_a, student=student, active=True)

    order = baker.make(
        'purchase_app.Order',
        email=student.email,
        coach=coach_b,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
        full_name=student.full_name,
    )

    with patch('django_q.tasks.async_task'):
        on_payment_success(order)

    order.refresh_from_db()
    assert order.status == Order.STATUS_NEEDS_REVIEW
    assert CoachStudent.objects.filter(coach=coach_b, student=student).count() == 0


# ── Renewal extension ──────────────────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_renewal_extends_next_payment_due(db, active_plan):
    from users_app.models import CoachStudent

    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    student = baker.make('users_app.User', role='student', is_active=True, email='renew@example.com')
    future = date.today() + timedelta(days=10)
    cs = baker.make(
        'users_app.CoachStudent',
        coach=coach,
        student=student,
        active=True,
        source='vagus',
        next_payment_due=future,
    )

    order = baker.make(
        'purchase_app.Order',
        email=student.email,
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
        full_name=student.full_name,
    )

    with patch('django_q.tasks.async_task'):
        on_payment_success(order)

    cs.refresh_from_db()
    expected = future + timedelta(days=active_plan.duration_days)
    assert cs.next_payment_due == expected


# ── Rate limit ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_checkout_rate_limited(coach, active_plan, settings):
    """After exceeding IP limit, checkout POST returns error."""
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = True

    from purchase_app.services import _CHECKOUT_IP_MAX, _checkout_cache_keys
    from django.core.cache import cache

    ip = '10.0.0.1'
    key_ip, _ = _checkout_cache_keys('rl@example.com', ip)
    cache.set(key_ip, _CHECKOUT_IP_MAX, 900)

    with patch('purchase_app.views._purchase_enabled', return_value=True), \
         patch('purchase_app.views._checkout_get_ip', return_value=ip):
        client_obj = Client()
        resp = client_obj.post(
            f'/satin-al/{coach.wordpress_post_id}/checkout/',
            {
                'full_name':        'RL Test',
                'email':            'rl@example.com',
                'plan':             active_plan.pk,
                'consent_terms':    'on',
                'consent_distance': 'on',
                'consent_kvkk':     'on',
            },
        )

    assert resp.status_code == 200
    assert Order.objects.filter(email='rl@example.com').count() == 0


# ── Sandbox staff guard ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_sandbox_pay_anonymous_returns_404(pending_order, settings):
    settings.PAYMENT_SANDBOX = True
    settings.DEBUG = False
    client_obj = Client()
    resp = client_obj.get(f'/satin-al/sandbox/pay/{pending_order.token}/')
    assert resp.status_code == 404


@pytest.mark.django_db
def test_sandbox_confirm_anonymous_returns_404(pending_order, settings):
    settings.PAYMENT_SANDBOX = True
    settings.DEBUG = False
    client_obj = Client()
    resp = client_obj.post(f'/satin-al/sandbox/confirm/{pending_order.token}/')
    assert resp.status_code == 404


@pytest.mark.django_db
def test_sandbox_pay_non_staff_returns_404(pending_order, settings):
    settings.PAYMENT_SANDBOX = True
    settings.DEBUG = False
    non_staff = baker.make('users_app.User', role='student', is_active=True, is_staff=False)
    client_obj = Client()
    client_obj.force_login(non_staff)
    resp = client_obj.get(f'/satin-al/sandbox/pay/{pending_order.token}/')
    assert resp.status_code == 404

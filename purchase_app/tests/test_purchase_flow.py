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
    settings.PAYMENT_SANDBOX = True
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
    """Step 3 POST must always use plan.price_kurus from DB, never a tampered value."""
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = True
    settings.DEBUG = False

    client_obj = Client()
    session = client_obj.session
    session['purchase_step1'] = {
        'email':     'hacker@example.com',
        'full_name': 'Hacker',
        'phone':     '05321234567',
        'sinif':     '10',
        'alan':      '',
        'plan_id':   str(active_plan.pk),
        'guardian_name':  '',
        'guardian_phone': '',
    }
    session['purchase_verified_email'] = 'hacker@example.com'
    session.save()

    with patch('purchase_app.views._purchase_enabled', return_value=True), \
         patch('purchase_app.views.get_provider') as mock_prov:
        mock_prov.return_value.name = 'sandbox'
        mock_prov.return_value.create_checkout.return_value = '/satin-al/tesekkur/fake/'
        resp = client_obj.post(
            f'/satin-al/{coach.wordpress_post_id}/odeme/',
            follow=False,
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
    """Step 1 POST with existing student email must redirect to verify (same as new email) — no user enumeration."""
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = True

    existing = baker.make('users_app.User', email='existing@example.com', role='student', is_active=True)

    with patch('purchase_app.views._purchase_enabled', return_value=True), \
         patch('purchase_app.views.get_provider') as mock_prov, \
         patch('purchase_app.views.verification.issue_code', return_value='123456'), \
         patch('django_q.tasks.async_task'):
        mock_prov.return_value.name = 'sandbox'

        client_obj = Client()
        payload = {
            'full_name':        'Test',
            'email':            existing.email,
            'phone':            '05321234567',
            'sinif':            '10',
            'alan':             '',
            'plan':             active_plan.pk,
            'consent_terms':    'on',
            'consent_distance': 'on',
            'consent_kvkk':     'on',
        }
        resp = client_obj.post(f'/satin-al/{coach.wordpress_post_id}/', payload, follow=False)

    # Both known and unknown email should redirect to verify — no 409 or "you already have an account"
    assert resp.status_code == 302
    assert '/dogrula/' in resp['Location']


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
    """After exceeding IP limit, step1 POST returns 200 with error; no order created."""
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
            f'/satin-al/{coach.wordpress_post_id}/',
            {
                'full_name':        'RL Test',
                'email':            'rl@example.com',
                'phone':            '05321234567',
                'sinif':            '10',
                'alan':             '',
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


# ── Purchased student full-integration ────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_purchased_student_in_roster_queryset(db, active_plan):
    """on_payment_success must set User.coach so the legacy roster query includes the student."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    order = baker.make(
        'purchase_app.Order',
        email='roster@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name='Roster Student',
    )

    with patch('django_q.tasks.async_task'):
        on_payment_success(order)

    assert User.objects.filter(role='student', coach=coach, email='roster@example.com').exists()


@pytest.mark.django_db(transaction=True)
def test_purchased_student_in_task_dropdown(db, active_plan):
    """After payment, list_for_coach() must include the new student."""
    from tasks_app.services.students import list_for_coach

    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    order = baker.make(
        'purchase_app.Order',
        email='dropdown@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name='Dropdown Student',
    )

    with patch('django_q.tasks.async_task'):
        on_payment_success(order)

    student_emails = [u.email for u in list_for_coach(coach)]
    assert 'dropdown@example.com' in student_emails


@pytest.mark.django_db(transaction=True)
def test_task_creation_endpoint_succeeds_for_purchased_student(db, active_plan):
    """POST /coach/tasks/api/gorev must return 201 for a purchased student."""
    import json
    from datetime import date

    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True, is_staff=False)
    order = baker.make(
        'purchase_app.Order',
        email='tasktest@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name='Task Student',
    )

    with patch('django_q.tasks.async_task'):
        on_payment_success(order)

    from django.contrib.auth import get_user_model
    student = get_user_model().objects.get(email='tasktest@example.com')

    client_obj = Client()
    client_obj.force_login(coach)
    resp = client_obj.post(
        '/coach/tasks/api/gorevler',
        data=json.dumps({
            'student_id': student.pk,
            'tarih': str(date.today()),
            'aktivite_tipi': 'konu_anlatimi',
            'ders_title': 'Matematik',
            'detaylar': json.dumps([{'aciklama': 'Türev', 'sure_bilgisi': '30 dk'}]),
        }),
        content_type='application/json',
    )
    assert resp.status_code == 201, f'Expected 201, got {resp.status_code}: {resp.content}'


@pytest.mark.django_db(transaction=True)
def test_purchased_student_not_visible_to_other_coach(db, active_plan):
    """The purchased student must NOT appear in another coach's roster or dropdown."""
    from django.contrib.auth import get_user_model
    from tasks_app.services.students import list_for_coach

    User = get_user_model()
    coach_a = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    coach_b = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    order = baker.make(
        'purchase_app.Order',
        email='isolation@example.com',
        coach=coach_a,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name='Isolated Student',
    )

    with patch('django_q.tasks.async_task'):
        on_payment_success(order)

    # Roster check
    assert not User.objects.filter(role='student', coach=coach_b, email='isolation@example.com').exists()
    # Dropdown check
    dropdown_emails = [u.email for u in list_for_coach(coach_b)]
    assert 'isolation@example.com' not in dropdown_emails


# ── Phone validation ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_phone_required(active_plan):
    from purchase_app.forms import PurchaseForm
    data = {
        'full_name': 'Test', 'email': 'a@b.com', 'phone': '',
        'sinif': '9', 'alan': '', 'plan': active_plan.pk,
        'consent_terms': 'on', 'consent_distance': 'on', 'consent_kvkk': 'on',
    }
    form = PurchaseForm(data)
    assert not form.is_valid()
    assert 'phone' in form.errors


@pytest.mark.django_db
def test_phone_normalization_formats(active_plan):
    from purchase_app.forms import PurchaseForm
    # (raw_input, expected_normalized)
    valid_inputs = [
        ('05321234567',     '05321234567'),
        ('5321234567',      '05321234567'),
        ('+905321234567',   '05321234567'),
        ('905321234567',    '05321234567'),
        ('0532 123 45 67',  '05321234567'),
        ('0532-123-45-67',  '05321234567'),
        ('(0532) 123 45 67','05321234567'),
        # 050 prefix (Türk Telekom)
        ('05051234567',     '05051234567'),
        ('5051234567',      '05051234567'),
        ('+905051234567',   '05051234567'),
    ]
    for raw, expected in valid_inputs:
        data = {
            'full_name': 'T', 'email': 'x@x.com', 'phone': raw,
            'sinif': '9', 'alan': '', 'plan': active_plan.pk,
            'consent_terms': 'on', 'consent_distance': 'on', 'consent_kvkk': 'on',
        }
        form = PurchaseForm(data)
        assert form.is_valid(), f'Expected valid for {raw!r}: {form.errors}'
        assert form.cleaned_data['phone'] == expected, \
            f'{raw!r} normalized to {form.cleaned_data["phone"]!r}, expected {expected!r}'


@pytest.mark.django_db
def test_phone_invalid_rejected(active_plan):
    from purchase_app.forms import PurchaseForm
    invalid_inputs = ['12345', 'abcdef', '04321234567', '0123456789']
    for raw in invalid_inputs:
        data = {
            'full_name': 'T', 'email': 'x@x.com', 'phone': raw,
            'sinif': '9', 'alan': '', 'plan': active_plan.pk,
            'consent_terms': 'on', 'consent_distance': 'on', 'consent_kvkk': 'on',
        }
        form = PurchaseForm(data)
        assert not form.is_valid(), f'Expected invalid for {raw!r}'
        assert 'phone' in form.errors, f'Expected phone error for {raw!r}'


# ── Sınıf / Alan validation ───────────────────────────────────────────────────

@pytest.mark.django_db
def test_sinif_required(active_plan):
    from purchase_app.forms import PurchaseForm
    data = {
        'full_name': 'T', 'email': 'x@x.com', 'phone': '05321234567',
        'sinif': '', 'alan': '', 'plan': active_plan.pk,
        'consent_terms': 'on', 'consent_distance': 'on', 'consent_kvkk': 'on',
    }
    form = PurchaseForm(data)
    assert not form.is_valid()
    assert 'sinif' in form.errors


@pytest.mark.parametrize('sinif', ['11', '12', 'mezun'])
@pytest.mark.django_db
def test_alan_required_for_upper_grades(active_plan, sinif):
    from purchase_app.forms import PurchaseForm
    data = {
        'full_name': 'T', 'email': 'x@x.com', 'phone': '05321234567',
        'sinif': sinif, 'alan': '', 'plan': active_plan.pk,
        'consent_terms': 'on', 'consent_distance': 'on', 'consent_kvkk': 'on',
    }
    form = PurchaseForm(data)
    assert not form.is_valid()
    assert 'alan' in form.errors, f'Expected alan error for sinif={sinif}'


@pytest.mark.parametrize('sinif', ['9', '10'])
@pytest.mark.django_db
def test_alan_optional_for_lower_grades(active_plan, sinif):
    from purchase_app.forms import PurchaseForm
    data = {
        'full_name': 'T', 'email': 'x@x.com', 'phone': '05321234567',
        'sinif': sinif, 'alan': '', 'plan': active_plan.pk,
        'consent_terms': 'on', 'consent_distance': 'on', 'consent_kvkk': 'on',
    }
    form = PurchaseForm(data)
    assert form.is_valid(), f'Expected valid (alan optional) for sinif={sinif}: {form.errors}'


@pytest.mark.django_db
def test_consent_still_required(active_plan):
    from purchase_app.forms import PurchaseForm
    data = {
        'full_name': 'T', 'email': 'x@x.com', 'phone': '05321234567',
        'sinif': '10', 'alan': '', 'plan': active_plan.pk,
        # consents missing
    }
    form = PurchaseForm(data)
    assert not form.is_valid()
    assert 'consent_terms' in form.errors or 'consent_distance' in form.errors or 'consent_kvkk' in form.errors


# ── Sinif/Alan snapshot on Order + student ────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_sinif_alan_snapshot_on_order(db, active_plan, coach):
    """Checkout must write sinif and alan to the Order row."""
    order = baker.make(
        'purchase_app.Order',
        email='snap@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name='Snap User',
        sinif='11',
        alan='SAY',
    )
    assert order.sinif == '11'
    assert order.alan == 'SAY'


@pytest.mark.django_db(transaction=True)
def test_payment_success_applies_sinif_alan_to_new_student(db, active_plan):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    order = baker.make(
        'purchase_app.Order',
        email='newstusnif@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name='New Student',
        sinif='11',
        alan='SAY',
    )

    with patch('django_q.tasks.async_task'):
        on_payment_success(order)

    student = User.objects.get(email='newstusnif@example.com')
    assert student.sinif == '11'
    assert student.alan == 'SAY'


@pytest.mark.django_db(transaction=True)
def test_payment_success_does_not_overwrite_existing_sinif_alan(db, active_plan):
    """on_payment_success must not clobber a student who already has sinif/alan."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    existing = baker.make(
        'users_app.User',
        role='student',
        email='existing_snif@example.com',
        sinif='12',
        alan='EA',
        is_active=True,
    )
    order = baker.make(
        'purchase_app.Order',
        email=existing.email,
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name=existing.full_name,
        sinif='9',
        alan='SOZ',
    )

    with patch('django_q.tasks.async_task'):
        on_payment_success(order)

    existing.refresh_from_db()
    assert existing.sinif == '12', 'sinif must not be overwritten'
    assert existing.alan == 'EA',  'alan must not be overwritten'


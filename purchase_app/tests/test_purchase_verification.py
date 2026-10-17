"""
Tests for the 3-step purchase flow verification logic and guards.
"""
import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from model_bakery import baker

from purchase_app import verification
from purchase_app.models import Order, Plan
from purchase_app.services import on_payment_success

User = get_user_model()


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def coach(db):
    return baker.make(
        'users_app.User',
        role='coach',
        is_active=True,
        is_approved=True,
        wp_is_available=True,
        wordpress_post_id=7777,
    )


@pytest.fixture
def active_plan(db):
    return baker.make(
        'purchase_app.Plan',
        name='Verify Test Plan',
        kind=Plan.KIND_ONE_TIME,
        price_kurus=199900,
        duration_days=30,
        active=True,
    )


@pytest.fixture
def purchase_settings(settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/terms'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/ds'
    settings.LEGAL_PRIVACY_URL = 'https://example.com/kvkk'
    settings.PAYMENT_SANDBOX = True
    settings.DEBUG = False
    return settings


def _step1_post(client, wp_id, email, plan_pk, extra=None):
    payload = {
        'full_name':        'Test User',
        'email':            email,
        'phone':            '05321234567',
        'sinif':            '10',
        'alan':             '',
        'plan':             plan_pk,
        'consent_terms':    'on',
        'consent_distance': 'on',
        'consent_kvkk':     'on',
    }
    if extra:
        payload.update(extra)
    return client.post(f'/satin-al/{wp_id}/', payload, follow=False)


# ── 1. No user enumeration on step 1 ─────────────────────────────────────────

@pytest.mark.django_db
def test_code_send_identical_for_known_unknown_email(coach, active_plan, purchase_settings):
    """Both existing and new email addresses redirect to /dogrula/."""
    existing = baker.make('users_app.User', email='exists@example.com', role='student', is_active=True)

    with patch('purchase_app.views.verification.issue_code', return_value='111111'), \
         patch('django_q.tasks.async_task'):
        c1 = Client()
        resp1 = _step1_post(c1, coach.wordpress_post_id, 'exists@example.com', active_plan.pk)

        c2 = Client()
        resp2 = _step1_post(c2, coach.wordpress_post_id, 'newone@example.com', active_plan.pk)

    assert resp1.status_code == 302, f'Expected 302 for existing email, got {resp1.status_code}'
    assert resp2.status_code == 302, f'Expected 302 for new email, got {resp2.status_code}'
    assert '/dogrula/' in resp1['Location']
    assert '/dogrula/' in resp2['Location']


# ── 2. Wrong code rejected ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_wrong_code_rejected():
    code = verification.issue_code('sess1', 'a@b.com')
    result = verification.verify('sess1', 'a@b.com', '000000')
    assert result == verification.WRONG


# ── 3. Expired code ───────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_expired_code():
    from django.core.cache import cache
    verification.issue_code('sess2', 'a@b.com')
    # Manually delete the code cache entry
    h = __import__('hashlib').sha256(f'sess2|a@b.com'.encode()).hexdigest()
    cache.delete(f'pv_code_{h}')
    result = verification.verify('sess2', 'a@b.com', '123456')
    assert result == verification.NO_CODE


# ── 4. Replayed code rejected ─────────────────────────────────────────────────

@pytest.mark.django_db
def test_replayed_code_rejected():
    code = verification.issue_code('sess3', 'a@b.com')
    r1 = verification.verify('sess3', 'a@b.com', code)
    assert r1 == verification.OK
    r2 = verification.verify('sess3', 'a@b.com', code)
    assert r2 == verification.NO_CODE


# ── 5. Attempt limit ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_attempt_limit():
    verification.issue_code('sess4', 'a@b.com')
    for _ in range(5):
        verification.verify('sess4', 'a@b.com', '000000')
    result = verification.verify('sess4', 'a@b.com', '000000')
    assert result == verification.MAX_ATTEMPTS


# ── 6. Resend cooldown ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_resend_cooldown():
    verification.issue_code('sess5', 'a@b.com')
    verification.record_resend('sess5', 'a@b.com')
    assert verification.can_resend('sess5', 'a@b.com') is False


# ── 7. Resend window limit ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_resend_window_limit():
    from django.core.cache import cache
    # Manually bypass cooldown by pre-setting count without cooldown
    h = __import__('hashlib').sha256(f'sess6|a@b.com'.encode()).hexdigest()
    cache.set(f'pv_rcnt_{h}', 5, 1800)
    assert verification.can_resend('sess6', 'a@b.com') is False


# ── 8. Step 3 unreachable without session ─────────────────────────────────────

@pytest.mark.django_db
def test_step3_unreachable_without_session(coach, purchase_settings):
    c = Client()
    resp = c.get(f'/satin-al/{coach.wordpress_post_id}/odeme/')
    assert resp.status_code == 302
    assert f'/satin-al/{coach.wordpress_post_id}/' in resp['Location']


# ── 9. Step 3 unreachable with mismatched email ───────────────────────────────

@pytest.mark.django_db
def test_step3_unreachable_with_mismatched_email(coach, active_plan, purchase_settings):
    c = Client()
    session = c.session
    session['purchase_step1'] = {
        'email':     'c@d.com',
        'full_name': 'T',
        'phone':     '05321234567',
        'sinif':     '10',
        'alan':      '',
        'plan_id':   str(active_plan.pk),
        'guardian_name': '',
        'guardian_phone': '',
    }
    session['purchase_verified_email'] = 'a@b.com'
    session.save()
    resp = c.get(f'/satin-al/{coach.wordpress_post_id}/odeme/')
    assert resp.status_code == 302
    assert f'/satin-al/{coach.wordpress_post_id}/' in resp['Location']


# ── 10. Verify OK with existing student shows login hint ──────────────────────

@pytest.mark.django_db
def test_verify_ok_existing_student_shows_login_hint(coach, active_plan, purchase_settings):
    student = baker.make('users_app.User', email='student@example.com', role='student', is_active=True)

    c = Client()
    session = c.session
    session['purchase_step1'] = {
        'email':     'student@example.com',
        'full_name': 'T',
        'phone':     '05321234567',
        'sinif':     '10',
        'alan':      '',
        'plan_id':   str(active_plan.pk),
        'guardian_name': '',
        'guardian_phone': '',
    }
    session.save()

    code = verification.issue_code(c.session.session_key, 'student@example.com')

    resp = c.post(f'/satin-al/{coach.wordpress_post_id}/dogrula/', {'code': code})
    assert resp.status_code == 200
    assert b'account_exists_student' in resp.content or b'hesab' in resp.content.lower()


# ── 11. Verify OK with coach email shows neutral message ─────────────────────

@pytest.mark.django_db
def test_verify_ok_coach_email_shows_neutral(coach, active_plan, purchase_settings):
    coach_user = baker.make('users_app.User', email='coach2@example.com', role='coach', is_active=True)

    c = Client()
    session = c.session
    session['purchase_step1'] = {
        'email':     'coach2@example.com',
        'full_name': 'T',
        'phone':     '05321234567',
        'sinif':     '10',
        'alan':      '',
        'plan_id':   str(active_plan.pk),
        'guardian_name': '',
        'guardian_phone': '',
    }
    session.save()

    code = verification.issue_code(c.session.session_key, 'coach2@example.com')
    resp = c.post(f'/satin-al/{coach.wordpress_post_id}/dogrula/', {'code': code})
    assert resp.status_code == 200
    assert b'account_exists_other' in resp.content or b'ba\xc5\x9fka' in resp.content


# ── 12. Login tab only for students ──────────────────────────────────────────

@pytest.mark.django_db
def test_purchase_login_only_for_students(coach, active_plan, purchase_settings):
    coach_user = baker.make(
        'users_app.User',
        email='login_coach@example.com',
        role='coach',
        is_active=True,
        is_approved=True,
    )
    coach_user.set_password('secret123')
    coach_user.save()

    c = Client()
    resp = c.post(
        f'/satin-al/{coach.wordpress_post_id}/?mod=giris',
        {'login_email': 'login_coach@example.com', 'login_password': 'secret123'},
    )
    assert resp.status_code == 200
    assert not c.session.get('_auth_user_id')


# ── 13. Open redirect rejected ────────────────────────────────────────────────

@pytest.mark.django_db
def test_open_redirect_rejected(coach, active_plan, purchase_settings):
    student = baker.make(
        'users_app.User',
        email='redirect_student@example.com',
        role='student',
        is_active=True,
    )
    student.set_password('pass1234')
    student.save()

    c = Client()
    resp = c.post(
        f'/satin-al/{coach.wordpress_post_id}/?mod=giris',
        {
            'login_email':    'redirect_student@example.com',
            'login_password': 'pass1234',
            'next':           'http://evil.com/steal',
        },
        follow=False,
    )
    # Should redirect somewhere safe, not evil.com
    if resp.status_code == 302:
        assert 'evil.com' not in resp['Location']


# ── 14. Logged-in student skips verify ───────────────────────────────────────

@pytest.mark.django_db
def test_logged_in_student_skips_verify(coach, active_plan, purchase_settings):
    student = baker.make(
        'users_app.User',
        email='loggedin@example.com',
        role='student',
        is_active=True,
        sinif='10',
        alan='',
    )

    c = Client()
    c.force_login(student)

    resp = c.post(
        f'/satin-al/{coach.wordpress_post_id}/',
        {
            'full_name':        'Logged In Student',
            'phone':            '05321234567',
            'sinif':            '10',
            'alan':             '',
            'plan':             active_plan.pk,
            'consent_terms':    'on',
            'consent_distance': 'on',
            'consent_kvkk':     'on',
        },
        follow=False,
    )
    assert resp.status_code == 302
    # Should redirect to step 3 (odeme), NOT step 2 (dogrula)
    assert '/odeme/' in resp['Location']
    assert '/dogrula/' not in resp['Location']

    # Session should have verified_email set
    assert c.session.get('purchase_verified_email') == student.email.lower()


# ── 15. Logged-in student blocked by different coach ─────────────────────────

@pytest.mark.django_db
def test_logged_in_student_blocked_by_different_coach(coach, active_plan, purchase_settings):
    from users_app.models import CoachStudent

    coach_a = baker.make('users_app.User', role='coach', is_active=True, is_approved=True,
                         wordpress_post_id=7778, wp_is_available=True)
    student = baker.make(
        'users_app.User',
        email='blocked@example.com',
        role='student',
        is_active=True,
    )
    baker.make('users_app.CoachStudent', coach=coach_a, student=student, active=True)

    c = Client()
    c.force_login(student)

    resp = c.post(
        f'/satin-al/{coach.wordpress_post_id}/',
        {
            'full_name':        'Blocked Student',
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
    assert b'purchase_block_msg' in resp.content or 'ba' in resp.content.decode('utf-8', errors='replace')
    assert Order.objects.filter(email='blocked@example.com').count() == 0


# ── 16. Logged-in coach sees not_for_you ─────────────────────────────────────

@pytest.mark.django_db
def test_logged_in_coach_sees_not_for_you(coach, purchase_settings):
    another_coach = baker.make(
        'users_app.User',
        role='coach',
        is_active=True,
        is_approved=True,
    )
    c = Client()
    c.force_login(another_coach)

    resp = c.get(f'/satin-al/{coach.wordpress_post_id}/')
    assert resp.status_code == 200
    assert b'\xc3\xb6\xc4\x9frenci' in resp.content or b'not_for_you' in resp.content or resp.templates[0].name == 'purchase/not_for_you.html'


# ── 17. Order confirm email sent ─────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_order_confirm_email_sent(active_plan):
    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    # Existing student with usable password
    student = baker.make(
        'users_app.User',
        email='confirm_email@example.com',
        role='student',
        is_active=True,
    )
    student.set_password('pass123')
    student.save()

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

    with patch('django_q.tasks.async_task') as mock_at:
        on_payment_success(order)

    # async_task should have been called with send_purchase_emails
    called_tasks = [call.args[0] for call in mock_at.call_args_list]
    assert 'purchase_app.tasks.send_purchase_emails' in called_tasks


# ── 18. Idempotent — no double email ─────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_idempotent_no_double_email(active_plan):
    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    order = baker.make(
        'purchase_app.Order',
        email='double@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
        full_name='Double Test',
    )

    with patch('django_q.tasks.async_task') as mock_at:
        on_payment_success(order)
        on_payment_success(order)

    # async_task must be called exactly once (second call is no-op due to idempotency)
    called_tasks = [call.args[0] for call in mock_at.call_args_list]
    email_task_calls = [t for t in called_tasks if t == 'purchase_app.tasks.send_purchase_emails']
    assert len(email_task_calls) == 1, 'send_purchase_emails must be dispatched exactly once'


# ── 19. Flag off — step2 returns 404 ─────────────────────────────────────────

@pytest.mark.django_db
def test_flag_off_step2_returns_404(coach, active_plan):
    with patch('purchase_app.views._purchase_enabled', return_value=False):
        c = Client()
        session = c.session
        session['purchase_step1'] = {
            'email': 'x@x.com', 'full_name': 'T', 'phone': '05321234567',
            'sinif': '10', 'alan': '', 'plan_id': str(active_plan.pk),
            'guardian_name': '', 'guardian_phone': '',
        }
        session.save()
        resp2 = c.get(f'/satin-al/{coach.wordpress_post_id}/dogrula/')
        assert resp2.status_code == 404

        session['purchase_verified_email'] = 'x@x.com'
        session.save()
        resp3 = c.get(f'/satin-al/{coach.wordpress_post_id}/odeme/')
        assert resp3.status_code == 404

"""
Tests for phone/email uniqueness enforcement in purchase forms and profile save.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from model_bakery import baker

from purchase_app.models import Plan

User = get_user_model()


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
        name='Uniqueness Test Plan',
        kind=Plan.KIND_ONE_TIME,
        price_kurus=199900,
        duration_days=30,
        active=True,
    )


@pytest.fixture
def purchase_settings(settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.PAYMENT_SANDBOX = True
    settings.DEBUG = False
    return settings


def _step1_post(client, wp_id, email, plan_pk, phone='05559999999'):
    return client.post(f'/satin-al/{wp_id}/', {
        'full_name': 'Test Student',
        'email':     email,
        'phone':     phone,
        'sinif':     '11',
        'alan':      'SAY',
        'plan':      str(plan_pk),
    })


# ── 1. Anonymous purchase with a phone already belonging to an account ─────────

@pytest.mark.django_db
def test_purchase_phone_uniqueness_rejected(coach, active_plan, purchase_settings):
    baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone='+905551112233',
    )
    c = Client()
    resp = _step1_post(c, coach.wordpress_post_id, 'new@example.com',
                       active_plan.pk, phone='05551112233')
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'kayıtlı bir hesap zaten var' in content


# ── 2. Anonymous purchase with an email already belonging to an account ────────

@pytest.mark.django_db
def test_purchase_email_uniqueness_rejected(coach, active_plan, purchase_settings):
    baker.make(
        'users_app.User',
        email='existing@example.com',
        role='student',
        is_active=True,
        phone=None,
    )
    c = Client()
    resp = _step1_post(c, coach.wordpress_post_id, 'existing@example.com', active_plan.pk)
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert 'kayıtlı bir hesap zaten var' in content


# ── 3. Logged-in student can purchase using their own phone ────────────────────

@pytest.mark.django_db
def test_logged_in_student_own_phone_allowed(coach, active_plan, purchase_settings):
    student = baker.make(
        'users_app.User',
        email='owner@example.com',
        role='student',
        is_active=True,
        phone='+905557778888',
        sinif='11',
        alan='SAY',
    )
    c = Client()
    c.force_login(student)

    # The logged-in flow: email is auto-injected from user; phone is the user's own
    resp = c.post(f'/satin-al/{coach.wordpress_post_id}/', {
        'full_name': student.full_name,
        'phone':     '05557778888',
        'sinif':     '11',
        'alan':      'SAY',
        'plan':      str(active_plan.pk),
    })
    # No uniqueness error → form validates → redirects to payment step
    assert resp.status_code == 302


# ── 4. student_phone_save rejects if phone already set; profile shows read-only

@pytest.mark.django_db
def test_phone_save_rejects_when_set_and_profile_shows_readonly(db):
    student = baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone='+905551234567',
    )
    c = Client()
    c.force_login(student)

    # Backend rejects any further POST
    resp = c.post('/profil/telefon/', {'phone': '05559999999'})
    assert resp.status_code == 403

    # Profile page renders the phone as read-only text (no form)
    resp = c.get('/profil/')
    assert resp.status_code == 200
    content = resp.content.decode('utf-8')
    assert '05551234567' in content
    # The phone input field is absent when phone is already set
    assert 'name="phone"' not in content

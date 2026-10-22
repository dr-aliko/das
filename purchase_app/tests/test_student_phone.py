"""
Tests for student phone: purchase prefill, profile edit, on_payment_success behaviour.
"""
import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client
from model_bakery import baker

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
        wordpress_post_id=8888,
    )


@pytest.fixture
def active_plan(db):
    return baker.make(
        'purchase_app.Plan',
        name='Phone Test Plan',
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


# ── 1. Purchase step1 prefills full_name and phone for logged-in student ──────

@pytest.mark.django_db
def test_purchase_step1_prefills_name_and_phone(coach, active_plan, purchase_settings):
    student = baker.make(
        'users_app.User',
        email='buyer@example.com',
        full_name='Ali Kaya',
        role='student',
        is_active=True,
        phone='+905551234567',
        sinif='11',
        alan='SAY',
    )
    c = Client()
    c.force_login(student)

    resp = c.get(f'/satin-al/{coach.wordpress_post_id}/')
    assert resp.status_code == 200

    content = resp.content.decode('utf-8')
    # full_name prefilled
    assert 'Ali Kaya' in content
    # phone prefilled in national format (E.164 → national conversion)
    assert '05551234567' in content


# ── 2. Profile phone edit: valid saves, invalid shows error ───────────────────

@pytest.mark.django_db
def test_student_phone_save_valid_and_invalid(db):
    student = baker.make(
        'users_app.User',
        role='student',
        is_active=True,
        phone=None,
    )
    c = Client()
    c.force_login(student)

    # Valid phone — should save as E.164 and redirect
    resp = c.post('/profil/telefon/', {'phone': '05559876543'})
    assert resp.status_code == 302
    student.refresh_from_db()
    assert student.phone == '+905559876543'

    # Phone already set — any POST must be rejected with 403
    resp = c.post('/profil/telefon/', {'phone': '12345'})
    assert resp.status_code == 403
    student.refresh_from_db()
    assert student.phone == '+905559876543'  # unchanged


# ── 3. on_payment_success: apply if empty, never overwrite ───────────────────

@pytest.mark.django_db(transaction=True)
def test_phone_apply_if_empty_and_never_overwrite(active_plan):
    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)

    # Student with no phone: phone should be applied
    student_empty = baker.make(
        'users_app.User',
        email='nophone@example.com',
        role='student',
        is_active=True,
        phone=None,
    )
    order_empty = baker.make(
        'purchase_app.Order',
        email=student_empty.email,
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name=student_empty.full_name,
        phone='05551112233',
    )
    with patch('django_q.tasks.async_task'):
        on_payment_success(order_empty)
    student_empty.refresh_from_db()
    assert student_empty.phone == '+905551112233'

    # Student with existing phone: phone must NOT be overwritten
    student_has = baker.make(
        'users_app.User',
        email='hasphone@example.com',
        role='student',
        is_active=True,
        phone='+905559999999',
    )
    order_has = baker.make(
        'purchase_app.Order',
        email=student_has.email,
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name=student_has.full_name,
        phone='05551112233',
    )
    with patch('django_q.tasks.async_task'):
        on_payment_success(order_has)
    student_has.refresh_from_db()
    assert student_has.phone == '+905559999999'  # unchanged


# ── 4. New account created by purchase gets order phone immediately ───────────

@pytest.mark.django_db(transaction=True)
def test_new_account_purchase_stores_phone(active_plan):
    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    order = baker.make(
        'purchase_app.Order',
        email='brand_new@example.com',
        coach=coach,
        plan=active_plan,
        amount_kurus=active_plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        full_name='Brand New Student',
        phone='05334445566',
    )
    assert not User.objects.filter(email='brand_new@example.com').exists()

    with patch('django_q.tasks.async_task'):
        on_payment_success(order)

    new_user = User.objects.get(email='brand_new@example.com')
    assert new_user.phone == '+905334445566'

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.urls import reverse
from model_bakery import baker

from purchase_app.models import Order, Plan
from purchase_app.services import _checkout_get_ip, on_payment_success
from users_app.models import CoachStudent

User = get_user_model()

CONSENTS = {
    'consent_age': 'on', 'consent_prelim': 'on',
    'consent_distance_refund': 'on', 'consent_service_start': 'on',
}


@pytest.fixture
def coach(db):
    return baker.make(User, role='coach', is_active=True, is_approved=True,
                      wp_is_available=True, wordpress_post_id=7777)


@pytest.fixture
def plan(db):
    return baker.make(Plan, name='Aylik', kind=Plan.KIND_ONE_TIME, price_kurus=199900,
                      duration_days=30, active=True)


@pytest.fixture
def bank_transfer(settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.PAYMENT_SANDBOX = False
    settings.DEBUG = False
    settings.PURCHASE_IBAN = 'TR330006100519786457841326'
    settings.PURCHASE_IBAN_HOLDER = 'Vagus'
    settings.PURCHASE_BANK_NAME = 'Banka'
    return settings


@pytest.fixture
def staff_client(db):
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    client = Client()
    client.force_login(staff)
    return client


def make_order(coach, plan, status, **kw):
    return baker.make(Order, email='buyer@example.com', coach=coach, plan=plan,
                      amount_kurus=plan.price_kurus, status=status,
                      provider='bank_transfer', full_name='Alici', **kw)


def test_checkout_ip_ignores_client_supplied_forwarded_hops():
    request = RequestFactory().post('/', HTTP_X_FORWARDED_FOR='6.6.6.6, 203.0.113.20')
    assert _checkout_get_ip(request) == '203.0.113.20'


def test_refunded_order_cannot_be_marked_paid(coach, plan):
    order = make_order(coach, plan, Order.STATUS_REFUNDED)

    on_payment_success(order)

    order.refresh_from_db()
    assert order.status == Order.STATUS_REFUNDED
    assert not User.objects.filter(email='buyer@example.com').exists()


def test_panel_cancel_keeps_paid_order_and_cancels_open_one(coach, plan, staff_client):
    paid = make_order(coach, plan, Order.STATUS_PAID)
    open_order = make_order(coach, plan, Order.STATUS_AWAITING_TRANSFER)

    staff_client.post(reverse('purchase_panel:order_cancel', args=[paid.pk]))
    staff_client.post(reverse('purchase_panel:order_cancel', args=[open_order.pk]))

    paid.refresh_from_db()
    open_order.refresh_from_db()
    assert paid.status == Order.STATUS_PAID
    assert open_order.status == Order.STATUS_CANCELLED


def test_repeated_payment_submit_reuses_open_order(coach, plan, bank_transfer):
    client = Client()
    session = client.session
    session['purchase_step1'] = {
        'email': 'repeat@example.com', 'full_name': 'Tekrar Alici', 'phone': '05321234567',
        'sinif': '10', 'alan': '', 'plan_id': str(plan.pk),
        'guardian_name': '', 'guardian_phone': '',
    }
    session['purchase_verified_email'] = 'repeat@example.com'
    session.save()
    url = reverse('purchase:payment', args=[coach.wordpress_post_id])

    with patch('django_q.tasks.async_task'):
        first = client.post(url, CONSENTS)
        second = client.post(url, CONSENTS)

    assert first.status_code == second.status_code == 302
    assert first['Location'] == second['Location']
    assert Order.objects.filter(email='repeat@example.com').count() == 1


def test_repeated_renewal_submit_reuses_open_order(coach, plan, bank_transfer):
    student = baker.make(User, role='student', is_active=True, email='renew@example.com',
                         full_name='Yenileyen')
    baker.make(CoachStudent, coach=coach, student=student, active=True,
               source=CoachStudent.SOURCE_VAGUS,
               next_payment_due=date.today() + timedelta(days=3))
    client = Client()
    client.force_login(student)
    url = reverse('student:paketim_yenile')

    with patch('django_q.tasks.async_task'):
        first = client.post(url, CONSENTS)
        second = client.post(url, CONSENTS)

    assert first.status_code == second.status_code == 302
    assert first['Location'] == second['Location']
    assert Order.objects.filter(student=student, is_renewal=True).count() == 1


def test_existing_account_probing_is_rate_limited(coach, plan, bank_transfer):
    baker.make(User, role='student', is_active=True, email='known@example.com')
    client = Client()
    url = reverse('purchase:page', args=[coach.wordpress_post_id])
    data = {'full_name': 'Merakli', 'email': 'known@example.com', 'phone': '0532 111 22 33',
            'sinif': '10', 'alan': '', 'plan': str(plan.pk)}

    for _ in range(3):
        body = client.post(url, data).content.decode('utf-8')
        assert 'zaten var' in body

    body = client.post(url, data).content.decode('utf-8')
    assert 'zaten var' not in body
    assert 'Çok fazla istek' in body


def test_plan_create_rejects_unknown_kind_and_survives_infinite_share(staff_client):
    url = reverse('purchase_panel:plan_create')

    resp = staff_client.post(url, {'name': 'Hatali', 'kind': 'bogus', 'price_kurus': '1000',
                                   'duration_days': '30', 'coach_share_tl': '0'})
    assert resp.status_code == 200
    assert not Plan.objects.filter(name='Hatali').exists()

    resp = staff_client.post(url, {'name': 'Sonsuz', 'kind': Plan.KIND_ONE_TIME,
                                   'price_kurus': '1000', 'duration_days': '30',
                                   'coach_share_tl': 'inf'})
    assert resp.status_code == 200
    assert Plan.objects.get(name='Sonsuz').coach_share_kurus == 0


@pytest.mark.django_db
def test_checkout_counter_keeps_full_window_and_fails_open():
    from unittest import mock
    from django.core.cache import cache
    from purchase_app import services

    email, ip = 'window@example.com', '203.0.113.31'
    keys = services._checkout_cache_keys(email, ip)
    cache.delete_many(keys)
    with mock.patch.object(cache, 'set', wraps=cache.set) as spy:
        services.increment_checkout_counters(email, ip)
        services.increment_checkout_counters(email, ip)
    assert len(spy.call_args_list) == 4
    assert all(c.args[2] == services._CHECKOUT_WINDOW for c in spy.call_args_list)
    assert [cache.get(k) for k in keys] == [2, 2]
    cache.delete_many(keys)

    with mock.patch.object(cache, 'get', side_effect=RuntimeError('cache down')):
        services.increment_checkout_counters(email, ip)

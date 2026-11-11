import sys
import types
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, RequestFactory
from django.urls import reverse
from model_bakery import baker

from users_app.forms import CoachRegistrationForm, InviteAcceptForm
from users_app.models import PushSubscription, StudentInvite
from users_app.utils import client_ip

User = get_user_model()

STRONG = 'Zor-Parola-4821'


@pytest.fixture
def student_client(db):
    student = baker.make(User, role='student', is_active=True)
    client = Client()
    client.force_login(student)
    return client


def test_client_ip_uses_last_forwarded_hop_then_real_ip():
    rf = RequestFactory()
    spoofed = rf.get('/', HTTP_X_FORWARDED_FOR='1.1.1.1, 203.0.113.9', REMOTE_ADDR='')
    assert client_ip(spoofed) == '203.0.113.9'

    real_ip_only = rf.get('/', HTTP_X_REAL_IP='198.51.100.7', REMOTE_ADDR='')
    assert client_ip(real_ip_only) == '198.51.100.7'

    garbage = rf.get('/', HTTP_X_FORWARDED_FOR='not-an-ip', REMOTE_ADDR='')
    assert client_ip(garbage) == '127.0.0.1'


@pytest.mark.django_db
def test_login_ip_limit_not_bypassed_by_rotating_first_forwarded_hop():
    from users_app.views import _IP_MAX_FAILURES, _LOGIN_RATE_MSG
    client = Client()
    url = reverse('users_app:login')
    for i in range(_IP_MAX_FAILURES):
        client.post(url, {'username': f'u{i}@example.com', 'password': 'wrong'},
                    HTTP_X_FORWARDED_FOR=f'10.0.0.{i}, 203.0.113.50')
    resp = client.post(url, {'username': 'fresh@example.com', 'password': 'wrong'},
                       HTTP_X_FORWARDED_FOR='10.9.9.9, 203.0.113.50')
    assert _LOGIN_RATE_MSG in resp.content.decode('utf-8')


@pytest.mark.django_db
def test_register_blocked_after_ip_limit():
    from users_app.views import _REGISTER_IP_MAX, _REGISTER_RATE_MSG, _register_rate_key
    rf_request = RequestFactory().post('/', REMOTE_ADDR='127.0.0.1')
    cache.set(_register_rate_key(rf_request), _REGISTER_IP_MAX, 3600)

    resp = Client().post(reverse('users_app:register'), {
        'full_name': 'Yeni Koc', 'email': 'limited@example.com', 'phone': '0505 123 45 67',
        'password1': STRONG, 'password2': STRONG,
    })

    assert resp.status_code == 200
    assert _REGISTER_RATE_MSG in resp.content.decode('utf-8')
    assert not User.objects.filter(email='limited@example.com').exists()


@pytest.mark.django_db
def test_page_views_are_not_rate_limited():
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    coach_client = Client()
    coach_client.force_login(coach)
    staff = baker.make(User, role='coach', is_active=True, is_approved=True, is_staff=True)
    staff_client = Client()
    staff_client.force_login(staff)

    with patch('users_app.services.wordpress.fetch_all_wp_coaches', return_value=[]):
        for _ in range(32):
            assert coach_client.get(reverse('users_app:coach_invites')).status_code == 200
            assert staff_client.get(reverse('panel_koc_ekle')).status_code == 200
            assert staff_client.get(reverse('staff_coach_documents')).status_code == 200


@pytest.mark.django_db
def test_invite_accept_double_submit_creates_one_account(settings):
    settings.COACH_PER_STUDENT_PERIODS = False
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    invite = baker.make(StudentInvite, coach=coach, email='once@example.com',
                        token=StudentInvite.generate_token(), is_used=False,
                        initiated_by_staff=False)
    data = {'full_name': 'Tek Kayit', 'password1': STRONG, 'password2': STRONG,
            'terms_accepted': 'on', 'kvkk_accepted': 'on'}
    url = reverse('users_app:invite_register', args=[invite.token])

    assert Client().post(url, data).status_code == 302
    assert Client().post(url, data).status_code == 404
    assert User.objects.filter(email='once@example.com').count() == 1


def test_feedback_rate_limited_and_recipients_from_settings(student_client, settings):
    settings.FEEDBACK_RECIPIENTS = ['destek@example.com']
    url = reverse('profil_geri_bildirim')

    for _ in range(10):
        assert student_client.post(url, {'tip': 'oneri', 'mesaj': 'x' * 9000}).status_code == 200
    assert student_client.post(url, {'tip': 'oneri', 'mesaj': 'bir daha'}).status_code == 429

    assert len(mail.outbox) == 10
    assert mail.outbox[0].to == ['destek@example.com']
    assert 'x' * 5001 not in mail.outbox[0].body


def test_push_subscribe_only_accepts_push_service_hosts(student_client):
    import json
    url = reverse('profil_push_subscribe')
    keys = {'p256dh': 'k', 'auth': 'a'}

    for endpoint in ('https://internal.example/hook',
                     'https://fcm.googleapis.com.evil.example/x',
                     'https://fcm.googleapis.com:8443/x'):
        resp = student_client.post(url, json.dumps({'endpoint': endpoint, 'keys': keys}),
                                   content_type='application/json')
        assert resp.status_code == 400
    assert not PushSubscription.objects.exists()

    for endpoint in ('https://updates.push.services.mozilla.com/wpush/v2/abc',
                     'https://web.push.apple.com/abc',
                     'https://wns2-par02p.notify.windows.com/w/?token=abc'):
        resp = student_client.post(url, json.dumps({'endpoint': endpoint, 'keys': keys}),
                                   content_type='application/json')
        assert resp.status_code == 200
    assert PushSubscription.objects.count() == 3


@pytest.mark.django_db
def test_push_network_error_is_counted_not_raised(settings):
    from users_app.services.notifications import send_push_notification
    settings.VAPID_PRIVATE_KEY = 'test-key'
    user = baker.make(User, role='student', is_active=True)
    baker.make(PushSubscription, user=user, endpoint='https://fcm.googleapis.com/fcm/send/x',
               p256dh='k', auth='a', is_active=True)

    def webpush(**kwargs):
        raise ConnectionError('down')

    fake_pywebpush = types.SimpleNamespace(
        webpush=webpush, WebPushException=type('WebPushException', (Exception,), {}),
    )
    with patch.dict(sys.modules, {'pywebpush': fake_pywebpush}):
        assert send_push_notification(user, 'Baslik', 'Govde') == (0, 1)


@pytest.mark.django_db
def test_registration_and_invite_forms_reject_weak_passwords():
    weak = CoachRegistrationForm({
        'full_name': 'Koc Deneme', 'email': 'weak@example.com', 'phone': '0505 123 45 67',
        'password1': '12345678', 'password2': '12345678',
    })
    assert not weak.is_valid()
    assert 'password2' in weak.errors

    strong = CoachRegistrationForm({
        'full_name': 'Koc Deneme', 'email': 'strong@example.com', 'phone': '0505 123 45 67',
        'password1': STRONG, 'password2': STRONG,
    })
    assert strong.is_valid(), strong.errors

    invite_weak = InviteAcceptForm({
        'full_name': 'Ogrenci', 'password1': 'password', 'password2': 'password',
        'terms_accepted': 'on', 'kvkk_accepted': 'on',
    })
    assert not invite_weak.is_valid()
    assert 'password2' in invite_weak.errors


def test_secret_key_required_when_debug_is_false():
    from core_config.settings import _INSECURE_DEV_SECRET_KEY, _resolve_secret_key

    assert _resolve_secret_key('real-secret', debug=False) == 'real-secret'
    assert _resolve_secret_key('', debug=True) == _INSECURE_DEV_SECRET_KEY
    with pytest.raises(ImproperlyConfigured):
        _resolve_secret_key('', debug=False)
    with pytest.raises(ImproperlyConfigured):
        _resolve_secret_key(_INSECURE_DEV_SECRET_KEY, debug=False)

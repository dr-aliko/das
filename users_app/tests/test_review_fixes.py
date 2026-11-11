import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import PushSubscription

User = get_user_model()


@pytest.fixture
def student_client(db):
    student = baker.make(User, role='student', is_active=True)
    client = Client()
    client.force_login(student)
    return client


@pytest.fixture
def coach_client(db):
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    client = Client()
    client.force_login(coach)
    return client


@pytest.mark.django_db
def test_invite_page_anonymous_without_remote_addr_redirects_to_login():
    resp = Client().get(reverse('users_app:coach_invites'), REMOTE_ADDR='')
    assert resp.status_code == 302
    assert reverse('users_app:login') in resp['Location']


def test_quick_update_ignores_foreign_referer(coach_client):
    url = reverse('coach_profile_quick_update')
    data = {'full_name': 'Yeni Ad', 'phone': '0505 123 45 67'}

    resp = coach_client.post(url, data, HTTP_REFERER='https://evil.example/x')
    assert resp.status_code == 302
    assert resp['Location'] == '/'

    resp = coach_client.post(url, data, HTTP_REFERER='http://testserver/coach/')
    assert resp['Location'] == 'http://testserver/coach/'


@pytest.mark.parametrize('payload', [[], ['alan'], {'alan': ['SAY']}, {'sinif': {'a': 1}}])
def test_alan_sinif_save_rejects_malformed_json(student_client, payload):
    resp = student_client.post(
        reverse('profil_alan_sinif'), json.dumps(payload), content_type='application/json',
    )
    assert resp.status_code == 400


def test_push_subscribe_requires_https_endpoint(student_client):
    url = reverse('profil_push_subscribe')
    keys = {'p256dh': 'k', 'auth': 'a'}

    resp = student_client.post(
        url, json.dumps({'endpoint': 'http://127.0.0.1:8000/internal', 'keys': keys}),
        content_type='application/json',
    )
    assert resp.status_code == 400
    assert not PushSubscription.objects.exists()

    resp = student_client.post(
        url, json.dumps({'endpoint': 'https://fcm.googleapis.com/fcm/send/abc', 'keys': keys}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    assert PushSubscription.objects.count() == 1

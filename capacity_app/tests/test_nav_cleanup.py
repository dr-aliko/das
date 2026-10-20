"""
Tests for nav cleanup:
- Staff capacity panel shows Ayarlar button
- Coach pages have no Ödeme takibi or Kontenjan nav; invites page keeps buy button
- Old coach billing URL redirects to /coach/kazanclar/
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from model_bakery import baker

User = get_user_model()


@pytest.fixture
def staff_user(db):
    u = baker.make(User, role='staff', is_active=True, is_staff=True)
    u.set_password('pw')
    u.save()
    return u


@pytest.fixture
def coach_user(db):
    u = baker.make(User, role='coach', is_active=True, is_approved=True)
    u.set_password('pw')
    u.save()
    return u


@pytest.fixture
def staff_client(staff_user):
    c = Client()
    c.login(username=staff_user.email, password='pw')
    return c


@pytest.fixture
def coach_client(coach_user):
    c = Client()
    c.login(username=coach_user.email, password='pw')
    return c


@pytest.mark.django_db
def test_capacity_panel_has_ayarlar_button(staff_client):
    """Staff capacity overview page has a link to the settings page."""
    resp = staff_client.get(reverse('capacity_panel:overview'))
    assert resp.status_code == 200
    settings_url = reverse('capacity_panel:settings')
    assert settings_url.encode() in resp.content


@pytest.mark.django_db
def test_coach_nav_no_odeme_or_kontenjan(coach_client, settings):
    """Coach dashboard has neither Ödeme takibi nor Kontenjan nav links."""
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('coach:dashboard'))
    assert resp.status_code == 200
    body = resp.content.decode('utf-8')
    assert 'Ödeme takibi' not in body
    # No standalone /coach/kontenjan nav link (buy button on invites is OK)
    assert '/coach/kontenjan/' not in body


@pytest.mark.django_db
def test_invites_page_keeps_buy_button(coach_client, settings):
    """Coach invites page retains the capacity purchase link."""
    settings.COACH_CAPACITY_ENFORCED = True
    resp = coach_client.get(reverse('users_app:coach_invites'))
    assert resp.status_code == 200
    capacity_url = reverse('capacity:page')
    assert capacity_url.encode() in resp.content


@pytest.mark.django_db
def test_old_coach_billing_url_redirects(coach_client):
    """GET /coach/odeme/ redirects coaches to /coach/kazanclar/."""
    resp = coach_client.get('/coach/odeme/')
    assert resp.status_code == 302
    assert '/coach/kazanclar/' in resp['Location']

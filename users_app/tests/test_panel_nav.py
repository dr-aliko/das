"""Panel navigation — shared nav widget is present on all staff pages."""
import pytest
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import CoachStudent, User


def _staff():
    return baker.make(User, role='coach', is_staff=True, is_active=True, is_approved=True)


def _coach():
    return baker.make(User, role='coach', is_active=True, is_approved=True)


def _student():
    return baker.make(User, role='student', is_active=True)


# ── 1. Parametrized smoke: all pure-DB panel pages return 200 ─────────────────

PANEL_URLS = [
    'panel_home',
    'panel_billing',
    'panel_odemeler',
    'panel_davetler',
    'panel_ogrenciler',
    'panel_koc_ekle',
    'staff_coach_documents',
]


@pytest.mark.django_db
@pytest.mark.parametrize('url_name', PANEL_URLS)
def test_panel_page_returns_200(url_name):
    c = Client()
    c.force_login(_staff())
    assert c.get(reverse(url_name)).status_code == 200


# ── 2. Nav widget is present and contains expected links ─────────────────────

@pytest.mark.django_db
def test_panel_nav_links_present():
    c = Client()
    c.force_login(_staff())
    content = c.get(reverse('panel_home')).content.decode()
    assert 'id="panel-main-nav"' in content
    for label in ('Genel bakış', 'Kontenjan', 'Kazançlar', 'Belgeler', 'Siparişler'):
        assert label in content, f'"{label}" missing from panel nav'


# ── 3. Secondary page highlights its parent section ──────────────────────────

@pytest.mark.django_db
def test_koc_degistir_has_panel_nav():
    staff = _staff()
    coach = _coach()
    student = _student()
    baker.make(CoachStudent, coach=coach, student=student, source='vagus', active=True)
    student.coach = coach
    student.save()

    c = Client()
    c.force_login(staff)
    response = c.get(reverse('panel_koc_degistir', args=[student.pk]))
    assert response.status_code == 200
    assert 'id="panel-main-nav"' in response.content.decode()


# ── 4. Coach-side pages must never render the panel nav ──────────────────────

@pytest.mark.django_db
def test_no_panel_nav_on_coach_billing():
    c = Client()
    c.force_login(_coach())
    content = c.get(reverse('coach_billing')).content.decode()
    assert 'id="panel-main-nav"' not in content

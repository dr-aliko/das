"""Panel navigation — two-level shared nav widget."""
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


# ── Smoke: pure-DB panel pages return 200 ────────────────────────────────────

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


# ── Nav test 1: all five group pills render ───────────────────────────────────

@pytest.mark.django_db
def test_group_pills_render():
    c = Client()
    c.force_login(_staff())
    content = c.get(reverse('panel_home')).content.decode()
    assert 'id="panel-main-nav"' in content
    for label in ('Genel bakış', 'Koçlar', 'Öğrenciler', 'Satış', 'Ödemeler'):
        assert label in content, f'group pill "{label}" missing from nav'


# ── Nav test 2: second row shows only the active group's pages ────────────────

@pytest.mark.django_db
def test_second_row_shows_only_active_group():
    c = Client()
    c.force_login(_staff())
    # panel_koc_ekle → active_section='koc_ekle' → group 'koclar'
    # second row must include 'Belgeler' (Koçlar group) and must NOT include 'Davetler' (Öğrenciler group)
    content = c.get(reverse('panel_koc_ekle')).content.decode()
    assert 'Belgeler' in content
    assert 'Davetler' not in content


# ── Nav test 3: removed pages absent from menu ───────────────────────────────

@pytest.mark.django_db
def test_removed_pages_not_in_nav():
    c = Client()
    c.force_login(_staff())
    content = c.get(reverse('panel_home')).content.decode()
    nav_start = content.find('id="panel-main-nav"')
    nav_end   = content.find('</div>', nav_start + 500)  # rough boundary
    nav_block = content[nav_start:nav_end]
    assert 'Tarifeler' not in nav_block
    assert 'Ödeme özeti' not in nav_block


# ── Secondary page still has the nav widget ──────────────────────────────────

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


# ── Coach-side pages must never render the panel nav ─────────────────────────

@pytest.mark.django_db
def test_no_panel_nav_on_coach_billing():
    c = Client()
    c.force_login(_coach())
    content = c.get(reverse('coach_billing')).content.decode()
    assert 'id="panel-main-nav"' not in content

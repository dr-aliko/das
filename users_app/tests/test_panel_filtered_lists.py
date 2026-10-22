"""Filtered list pages — counter accuracy, banner behaviour, access control."""
import pytest
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import CoachProfile, CoachStudent, User
from users_app.panel_badges import all_badges, qs_docs, qs_overdue


# ── Test 1: badge counter equals queryset length for two counters ─────────────

@pytest.mark.django_db
def test_counter_matches_queryset_length():
    for _ in range(2):
        coach = baker.make(User, role='coach', is_active=True, is_approved=True)
        baker.make(CoachProfile, user=coach, document_status='pending', document='a/b.pdf')

    overdue_coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(
        CoachStudent,
        coach=overdue_coach,
        source='vagus',
        active=True,
        next_payment_due='2000-01-01',
    )

    badges = all_badges()
    assert badges['docs'] == len(list(qs_docs()))
    assert badges['overdue'] == len(list(qs_overdue()))


# ── Test 2: banner shown on known filter, absent on unknown filter ────────────

@pytest.mark.django_db
def test_filter_banner_and_unknown_ignored():
    staff = baker.make(User, role='coach', is_staff=True, is_active=True, is_approved=True)
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(CoachProfile, user=coach, document_status='pending', document='x/y.pdf')

    c = Client()
    c.force_login(staff)

    resp = c.get(reverse('staff_coach_documents') + '?filtre=documents-pending')
    assert resp.status_code == 200
    assert 'kayıt gösteriliyor' in resp.content.decode()

    resp2 = c.get(reverse('staff_coach_documents') + '?filtre=xyz_garbage_unknown')
    assert resp2.status_code == 200
    assert 'kayıt gösteriliyor' not in resp2.content.decode()


# ── Test 3: non-staff cannot reach filtered pages ─────────────────────────────

@pytest.mark.django_db
def test_filtered_pages_require_staff():
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    c = Client()
    c.force_login(coach)

    for url_name, qs in [
        ('staff_coach_documents', '?filtre=no-iban'),
        ('panel_ogrenciler',      '?filtre=vagus-ended'),
        ('panel_wp_koclar',       '?filtre=wp-unmatched'),
    ]:
        resp = c.get(reverse(url_name) + qs)
        assert resp.status_code in (302, 403), (
            f'{url_name} returned {resp.status_code} for non-staff coach'
        )

"""Belgeler page: profile-issues always visible, badge matches queryset, unknown filter ignored."""
import pytest
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import CoachProfile, User


# ── Test 1: Belgeler page (no filter) shows profile-issue coaches; badge == queryset ──

@pytest.mark.django_db
def test_belgeler_page_lists_profile_issues_no_filter():
    staff = baker.make(User, role='coach', is_staff=True, is_active=True, is_approved=True)
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(CoachProfile, user=coach, iban='', document='', phone='')

    from users_app.panel_badges import _belgeler, qs_profile_issues
    assert _belgeler() == qs_profile_issues().count()
    assert _belgeler() >= 1

    c = Client()
    c.force_login(staff)
    resp = c.get(reverse('staff_coach_documents'))
    assert resp.status_code == 200
    assert coach.full_name.encode() in resp.content


# ── Test 2: Unknown filtre value silently ignored — no banner ─────────────────

@pytest.mark.django_db
def test_unknown_filtre_ignored_no_banner():
    staff = baker.make(User, role='coach', is_staff=True, is_active=True, is_approved=True)
    c = Client()
    c.force_login(staff)
    resp = c.get(reverse('staff_coach_documents') + '?filtre=xyz_garbage_unknown')
    assert resp.status_code == 200
    assert 'kayıt gösteriliyor' not in resp.content.decode()

"""Belgeler page: profile-issues always visible, badge narrower than queryset, unknown filter ignored."""
import pytest
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import CoachProfile, CoachStudent, User


# ── Test 1: Belgeler page shows all coaches with issues; badge counts only those with workload ──

@pytest.mark.django_db
def test_belgeler_page_lists_profile_issues_no_filter():
    staff = baker.make(User, role='coach', is_staff=True, is_active=True, is_approved=True)
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(CoachProfile, user=coach, iban='', document='', phone='')
    # Give coach workload so it counts in the badge
    student = baker.make(User, role='student', is_active=True)
    baker.make(CoachStudent, coach=coach, student=student, active=True, source='vagus', next_payment_due='2099-01-01')

    from users_app.panel_badges import _belgeler, qs_profile_issues
    # Badge only counts coaches with workload; list queryset shows all coaches with issues
    assert _belgeler() >= 1
    assert qs_profile_issues().count() >= _belgeler()
    assert coach.pk in qs_profile_issues().values_list('pk', flat=True)

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

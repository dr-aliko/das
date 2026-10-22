"""Panel badge counters — accuracy, fail-open, and nav rendering."""
import pytest
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import CoachProfile, CoachStudent, User
from users_app.panel_badges import all_badges


# ── Test 1: counter accuracy ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_badges_count_accurately():
    # Coach 1: pending document, valid IBAN → counted in docs and belgeler
    coach1 = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(CoachProfile, user=coach1, document_status='pending', document='some/path.pdf', iban='TR330006100519786457841326')

    # Coach 2: no IBAN, approved doc → counted in no_iban and belgeler (not in docs)
    coach2 = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(CoachProfile, user=coach2, document_status='approved', document='other/path.pdf', iban='')

    # One overdue active student
    overdue_coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(
        CoachStudent,
        coach=overdue_coach,
        source='vagus',
        active=True,
        next_payment_due='2000-01-01',
    )

    from users_app.panel_badges import _belgeler, qs_profile_issues
    badges = all_badges()

    assert badges['docs'] >= 1        # coach1 has pending doc
    assert badges['no_iban'] >= 1     # coach2 has no IBAN
    assert badges['overdue'] >= 1     # overdue student
    assert badges['belgeler'] == _belgeler()   # badge uses qs_profile_issues, not docs+no_iban
    assert badges['belgeler'] >= 2    # both coach1 and coach2 have issues
    assert badges['any_pending'] is True


# ── Test 2: exception in a counter → 0, page still loads ─────────────────────

@pytest.mark.django_db
def test_safe_returns_zero_on_exception(monkeypatch):
    import users_app.panel_badges as pb

    # Make every individual counter raise
    def _boom():
        raise RuntimeError("db gone")

    monkeypatch.setattr(pb, '_docs', _boom)
    monkeypatch.setattr(pb, '_transfers_purchase', _boom)
    monkeypatch.setattr(pb, '_transfers_capacity', _boom)
    monkeypatch.setattr(pb, '_earnings', _boom)
    monkeypatch.setattr(pb, '_no_iban', _boom)
    monkeypatch.setattr(pb, '_no_wp', _boom)
    monkeypatch.setattr(pb, '_overdue', _boom)
    monkeypatch.setattr(pb, '_belgeler', _boom)

    badges = all_badges()
    assert badges['docs'] == 0
    assert badges['koclar'] == 0
    assert badges['any_pending'] is False

    # Page must still return 200 even when all counters fail
    staff = baker.make(User, role='coach', is_staff=True, is_active=True, is_approved=True)
    c = Client()
    c.force_login(staff)
    assert c.get(reverse('panel_home')).status_code == 200


# ── Test 3: staff sees badges in nav; non-staff does not trigger all_badges ───

@pytest.mark.django_db
def test_staff_gets_badges_non_staff_does_not(monkeypatch):
    calls = []

    import users_app.panel_badges as pb
    real_all_badges = pb.all_badges

    def tracked_all_badges():
        calls.append(1)
        return real_all_badges()

    monkeypatch.setattr(pb, 'all_badges', tracked_all_badges)

    # Also patch the import inside the tag so monkeypatch takes effect
    import users_app.templatetags.panel_nav_tags as tag_mod

    def tag_all_badges():
        calls.append(1)
        return real_all_badges()

    monkeypatch.setattr(tag_mod, 'all_badges', tag_all_badges, raising=False)

    staff = baker.make(User, role='coach', is_staff=True, is_active=True, is_approved=True)
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)

    c = Client()

    # Non-staff coach hitting a coach page — all_badges must NOT be called
    calls.clear()
    c.force_login(coach)
    c.get(reverse('coach_billing'))
    assert len(calls) == 0, "all_badges called for non-staff user"

    # Staff hitting panel home — all_badges must be called (once from view, once from tag)
    calls.clear()
    c.force_login(staff)
    resp = c.get(reverse('panel_home'))
    assert resp.status_code == 200
    assert len(calls) >= 1, "all_badges never called for staff user"

"""Panel badge counters — accuracy, fail-open, workload filter, and cache invalidation."""
import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import CoachProfile, CoachStudent, User
from users_app.panel_badges import all_badges, invalidate_panel_badges


# ── Test 1: counter accuracy ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_badges_count_accurately():
    # Coach 1: pending document, valid IBAN → must have workload to count
    coach1 = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(CoachProfile, user=coach1, document_status='pending', document='some/path.pdf', iban='TR330006100519786457841326')
    student1 = baker.make(User, role='student', is_active=True)
    baker.make(CoachStudent, coach=coach1, student=student1, active=True, source='vagus', next_payment_due='2099-01-01')

    # Coach 2: no IBAN, approved doc → must have workload to count
    coach2 = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(CoachProfile, user=coach2, document_status='approved', document='other/path.pdf', iban='')
    student2 = baker.make(User, role='student', is_active=True)
    baker.make(CoachStudent, coach=coach2, student=student2, active=True, source='vagus', next_payment_due='2099-01-01')

    # One overdue active student (separate coach)
    overdue_coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(
        CoachStudent,
        coach=overdue_coach,
        source='vagus',
        active=True,
        next_payment_due='2000-01-01',
    )

    from users_app.panel_badges import _belgeler
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
    monkeypatch.setattr(pb, '_renewals_claimed', _boom)

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

    import users_app.templatetags.panel_nav_tags as tag_mod

    def tag_all_badges():
        calls.append(1)
        return real_all_badges()

    monkeypatch.setattr(tag_mod, 'all_badges', tag_all_badges, raising=False)

    staff = baker.make(User, role='coach', is_staff=True, is_active=True, is_approved=True)
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)

    c = Client()

    calls.clear()
    c.force_login(coach)
    c.get(reverse('coach_billing'))
    assert len(calls) == 0, "all_badges called for non-staff user"

    calls.clear()
    c.force_login(staff)
    resp = c.get(reverse('panel_home'))
    assert resp.status_code == 200
    assert len(calls) >= 1, "all_badges never called for staff user"


# ── Test 4: invalidate_panel_badges deletes only pbadge: keys ────────────────

@pytest.mark.django_db
def test_invalidate_panel_badges_selective():
    cache.set('pbadge:docs', 5, 120)
    cache.set('pbadge:no_iban', 3, 120)
    cache.set('login_pair_someuser', 'ratelimit_data', 120)  # unrelated key — must survive

    invalidate_panel_badges('pbadge:docs', 'pbadge:no_iban')

    assert cache.get('pbadge:docs') is None
    assert cache.get('pbadge:no_iban') is None
    assert cache.get('login_pair_someuser') == 'ratelimit_data'  # untouched

    # Test no-arg form deletes all pbadge: entries
    cache.set('pbadge:earnings', 7, 120)
    cache.set('pbadge:overdue', 2, 120)
    cache.set('other_key', 'keep', 120)

    invalidate_panel_badges()

    assert cache.get('pbadge:earnings') is None
    assert cache.get('pbadge:overdue') is None
    assert cache.get('other_key') == 'keep'


# ── Test 5: narrower coach definition — no workload → not counted ─────────────

@pytest.mark.django_db
def test_narrower_coach_definition():
    # Coach with no students and no earnings: should NOT appear in no_iban badge
    idle_coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(CoachProfile, user=idle_coach, iban='')

    # Coach with an active student and no IBAN: SHOULD appear in no_iban badge
    active_coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    baker.make(CoachProfile, user=active_coach, iban='')
    student = baker.make(User, role='student', is_active=True)
    baker.make(CoachStudent, coach=active_coach, student=student, active=True, source='vagus', next_payment_due='2099-01-01')

    from users_app.panel_badges import _no_iban
    count = _no_iban()

    # active_coach counted; idle_coach not counted
    from users_app.panel_badges import qs_no_iban
    all_no_iban_ids = set(qs_no_iban().values_list('pk', flat=True))
    assert active_coach.pk in all_no_iban_ids
    assert idle_coach.pk in all_no_iban_ids  # qs_ is unfiltered — list views still see it
    assert count >= 1  # at least active_coach counted
    # idle_coach must NOT inflate the badge counter
    from users_app.panel_badges import _coaches_with_workload_ids
    wids = _coaches_with_workload_ids()
    assert active_coach.pk in wids
    assert idle_coach.pk not in wids


# ── Test 6: doc approve via staff view clears docs badge immediately ──────────

@pytest.mark.django_db(transaction=True)
def test_badge_cleared_after_doc_approve():
    # Prime the docs badge with a known value
    cache.set('pbadge:docs', 99, 120)
    assert all_badges()['docs'] == 99  # served from cache

    # Approve the doc via the actual staff view so on_commit fires
    staff = baker.make(User, role='coach', is_staff=True, is_active=True, is_approved=True)
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    profile = baker.make(
        CoachProfile,
        user=coach,
        document_status='pending',
        document='doc/path.pdf',
        iban='TR330006100519786457841326',
    )
    student = baker.make(User, role='student', is_active=True)
    baker.make(CoachStudent, coach=coach, student=student, active=True, source='vagus', next_payment_due='2099-01-01')

    c = Client()
    c.force_login(staff)
    resp = c.post(
        reverse('staff_coach_document_action', kwargs={'pk': profile.pk}),
        {'action': 'approve'},
    )
    assert resp.status_code in (200, 302)

    # Cache entry must be gone — next call recomputes from DB
    assert cache.get('pbadge:docs') is None
    assert cache.get('pbadge:belgeler') is None

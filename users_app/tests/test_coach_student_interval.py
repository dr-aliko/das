"""
Tests for CoachStudentInterval and the coach_student service.

Covers:
- open/close interval on every transition type
- backfill (rebuild_intervals)
- at most one open interval per student
- reassign keeps source / next_payment_due / User.coach consistent
- reactivation of a prior link during reassign
- all refusals (same coach, inactive, unapproved, non-coach)
- old coach loses access, new coach gains access after reassign
- drift guard: service deactivation closes the interval
"""
import pytest
from datetime import date, timedelta

from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import CoachStudent, CoachStudentInterval, User
from users_app.services.coach_student import (
    close_interval,
    deactivate_link,
    ensure_active_link,
    open_interval,
    reassign_student,
    rebuild_intervals,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def make_coach(**kwargs):
    return baker.make(User, role='coach', is_active=True, is_approved=True, **kwargs)


def make_student(**kwargs):
    return baker.make(User, role='student', is_active=True, is_approved=True, **kwargs)


def make_link(coach, student, *, active=True, source='vagus', next_payment_due=None):
    return baker.make(
        CoachStudent,
        coach=coach,
        student=student,
        active=active,
        source=source,
        next_payment_due=next_payment_due,
        deactivation_reason=None if active else 'manual',
    )


# ── interval open / close ─────────────────────────────────────────────────────

@pytest.mark.django_db
def test_open_interval_creates_row():
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student)

    open_interval(link)

    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1


@pytest.mark.django_db
def test_close_interval_sets_ended_at_and_reason():
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student)
    open_interval(link)

    close_interval(link, CoachStudentInterval.REASON_MANUAL)

    interval = CoachStudentInterval.objects.get(coach=coach, student=student)
    assert interval.ended_at is not None
    assert interval.close_reason == CoachStudentInterval.REASON_MANUAL


@pytest.mark.django_db
def test_close_interval_idempotent_when_already_closed():
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student)
    open_interval(link)
    close_interval(link, CoachStudentInterval.REASON_MANUAL)

    close_interval(link, CoachStudentInterval.REASON_MANUAL)

    assert CoachStudentInterval.objects.filter(coach=coach, student=student).count() == 1


@pytest.mark.django_db
def test_deactivate_link_closes_interval_and_marks_link():
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student)
    open_interval(link)

    deactivate_link(link, CoachStudentInterval.REASON_PAYMENT_OVERDUE)

    link.refresh_from_db()
    assert link.active is False
    assert link.deactivation_reason == 'payment_overdue'
    interval = CoachStudentInterval.objects.get(coach=coach, student=student)
    assert interval.ended_at is not None
    assert interval.close_reason == 'payment_overdue'


@pytest.mark.django_db
def test_ensure_active_link_creates_and_opens_interval():
    coach = make_coach()
    student = make_student()

    link, created, reactivated = ensure_active_link(coach, student, 'vagus')

    assert created is True
    assert reactivated is False
    assert link.active is True
    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1


@pytest.mark.django_db
def test_ensure_active_link_reactivates_inactive_and_opens_interval():
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student, active=False)
    # Closed interval for the original period
    open_interval(link)
    close_interval(link, CoachStudentInterval.REASON_MANUAL)

    _, created, reactivated = ensure_active_link(coach, student, 'vagus')

    assert created is False
    assert reactivated is True
    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1


@pytest.mark.django_db
def test_ensure_active_link_no_double_interval_when_already_active():
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student, active=True)
    open_interval(link)

    ensure_active_link(coach, student, 'vagus')

    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1


# ── backfill ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_rebuild_intervals_active_links_get_open_intervals():
    coach = make_coach()
    student = make_student()
    make_link(coach, student, active=True)

    rebuild_intervals()

    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1


@pytest.mark.django_db
def test_rebuild_intervals_inactive_links_get_backfill_reason():
    coach = make_coach()
    student = make_student()
    make_link(coach, student, active=False)

    rebuild_intervals()

    interval = CoachStudentInterval.objects.get(coach=coach, student=student)
    assert interval.ended_at is not None
    assert interval.close_reason == CoachStudentInterval.REASON_BACKFILL


@pytest.mark.django_db
def test_rebuild_intervals_is_idempotent():
    coach = make_coach()
    student = make_student()
    make_link(coach, student, active=True)

    rebuild_intervals()
    rebuild_intervals()

    assert CoachStudentInterval.objects.filter(coach=coach, student=student).count() == 1


# ── at-most-one-open invariant ────────────────────────────────────────────────

@pytest.mark.django_db
def test_at_most_one_open_interval_per_student_after_reassign():
    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(old_coach, student)
    open_interval(link)

    reassign_student(student, new_coach, staff)

    open_intervals = CoachStudentInterval.objects.filter(
        student=student, ended_at__isnull=True
    )
    assert open_intervals.count() == 1
    assert open_intervals.first().coach_id == new_coach.pk


# ── reassign ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_reassign_keeps_source_and_next_payment_due():
    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    due = date.today() + timedelta(days=15)
    link = make_link(old_coach, student, source='vagus', next_payment_due=due)
    open_interval(link)

    reassign_student(student, new_coach, staff)

    new_link = CoachStudent.objects.get(coach=new_coach, student=student)
    assert new_link.source == 'vagus'
    assert new_link.next_payment_due == due
    assert new_link.active is True


@pytest.mark.django_db
def test_reassign_updates_user_coach_fk():
    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student(coach=old_coach)
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(old_coach, student)
    open_interval(link)

    reassign_student(student, new_coach, staff)

    student.refresh_from_db()
    assert student.coach_id == new_coach.pk


@pytest.mark.django_db
def test_reassign_deactivates_old_link():
    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(old_coach, student)
    open_interval(link)

    reassign_student(student, new_coach, staff)

    link.refresh_from_db()
    assert link.active is False
    assert link.deactivation_reason == CoachStudent.DEACTIVATION_REASSIGN


@pytest.mark.django_db
def test_reassign_closes_old_interval_with_reassign_reason():
    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(old_coach, student)
    open_interval(link)

    reassign_student(student, new_coach, staff)

    old_interval = CoachStudentInterval.objects.get(coach=old_coach, student=student)
    assert old_interval.ended_at is not None
    assert old_interval.close_reason == CoachStudentInterval.REASON_REASSIGN


@pytest.mark.django_db
def test_reassign_reactivates_prior_inactive_link():
    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)

    # Student was with new_coach before; that link is inactive
    prior_link = make_link(new_coach, student, active=False)
    open_interval(prior_link)
    close_interval(prior_link, CoachStudentInterval.REASON_MANUAL)

    # Now student is with old_coach
    current_link = make_link(old_coach, student, active=True)
    open_interval(current_link)

    reassign_student(student, new_coach, staff)

    prior_link.refresh_from_db()
    assert prior_link.active is True
    assert CoachStudent.objects.filter(coach=new_coach, student=student).count() == 1


# ── refusals ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_reassign_refuses_same_coach():
    coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(coach, student)
    open_interval(link)

    with pytest.raises(ValueError, match='zaten bu koçta'):
        reassign_student(student, coach, staff)


@pytest.mark.django_db
def test_reassign_refuses_inactive_target():
    old_coach = make_coach()
    new_coach = baker.make(User, role='coach', is_active=False, is_approved=True)
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(old_coach, student)
    open_interval(link)

    with pytest.raises(ValueError, match='pasif'):
        reassign_student(student, new_coach, staff)


@pytest.mark.django_db
def test_reassign_refuses_unapproved_target():
    old_coach = make_coach()
    new_coach = baker.make(User, role='coach', is_active=True, is_approved=False)
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(old_coach, student)
    open_interval(link)

    with pytest.raises(ValueError, match='onaylı değil'):
        reassign_student(student, new_coach, staff)


@pytest.mark.django_db
def test_reassign_refuses_non_coach_target():
    old_coach = make_coach()
    new_coach = baker.make(User, role='student', is_active=True, is_approved=True)
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(old_coach, student)
    open_interval(link)

    with pytest.raises(ValueError, match='koç değil'):
        reassign_student(student, new_coach, staff)


@pytest.mark.django_db
def test_reassign_refuses_when_no_active_link():
    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)

    with pytest.raises(ValueError, match='aktif bir koç bağlantısı'):
        reassign_student(student, new_coach, staff)


# ── access checks ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_old_coach_loses_student_after_reassign():
    """list_for_coach no longer returns the student for the old coach."""
    from tasks_app.services.students import list_for_coach

    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(old_coach, student)
    open_interval(link)
    student.coach = old_coach
    student.save(update_fields=['coach'])

    reassign_student(student, new_coach, staff)

    assert student not in list(list_for_coach(old_coach))


@pytest.mark.django_db
def test_new_coach_gains_student_after_reassign():
    """list_for_coach returns the student for the new coach."""
    from tasks_app.services.students import list_for_coach

    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student()
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    link = make_link(old_coach, student)
    open_interval(link)
    student.coach = old_coach
    student.save(update_fields=['coach'])

    reassign_student(student, new_coach, staff)

    assert student in list(list_for_coach(new_coach))


# ── drift guard ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_drift_guard_service_deactivation_closes_interval():
    """
    Drift guard: deactivating via the service closes the interval.
    If a future change introduces direct .update(active=False) that bypasses
    deactivate_link(), the interval will be left open and this test will NOT
    catch that specific bypass — but all other tests that verify the closed
    interval after a service call will fail, serving as the drift signal.
    """
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student, active=True)
    open_interval(link)

    deactivate_link(link, CoachStudentInterval.REASON_MANUAL)

    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 0
    link.refresh_from_db()
    assert link.active is False


@pytest.mark.django_db
def test_drift_guard_direct_update_does_not_close_interval():
    """
    Proves that CoachStudent.objects.update(active=False) does NOT close the
    interval, confirming why all deactivations must use deactivate_link().
    """
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student, active=True)
    open_interval(link)

    CoachStudent.objects.filter(pk=link.pk).update(active=False)

    # The interval is still open — direct update bypassed the service
    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1


# ── staff view ────────────────────────────────────────────────────────────────

@pytest.fixture
def staff_client(db):
    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    c = Client()
    c.force_login(staff)
    return c, staff


@pytest.mark.django_db
def test_koc_degistir_get_renders_confirm_page(staff_client):
    client, _ = staff_client
    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student()
    link = make_link(old_coach, student)
    open_interval(link)

    url = reverse('panel_koc_degistir', args=[student.pk])
    response = client.get(url)

    assert response.status_code == 200
    assert 'eligible_coaches' in response.context


@pytest.mark.django_db
def test_koc_degistir_post_executes_reassign(staff_client):
    client, _ = staff_client
    old_coach = make_coach()
    new_coach = make_coach()
    student = make_student(coach=old_coach)
    link = make_link(old_coach, student)
    open_interval(link)

    url = reverse('panel_koc_degistir', args=[student.pk])
    response = client.post(url, {'new_coach_id': new_coach.pk})

    assert response.status_code == 302
    student.refresh_from_db()
    assert student.coach_id == new_coach.pk


@pytest.mark.django_db
def test_koc_degistir_post_refuses_same_coach(staff_client):
    client, _ = staff_client
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student)
    open_interval(link)

    url = reverse('panel_koc_degistir', args=[student.pk])
    response = client.post(url, {'new_coach_id': coach.pk})

    assert response.status_code == 200
    assert response.context['error'] is not None


@pytest.mark.django_db
def test_koc_degistir_requires_staff(db):
    plain_coach = make_coach()
    student = make_student()
    c = Client()
    c.force_login(plain_coach)

    url = reverse('panel_koc_degistir', args=[student.pk])
    response = c.get(url)

    assert response.status_code in (302, 403)


# ── regression: renewal interval ─────────────────────────────────────────────

@pytest.mark.django_db(transaction=True)
def test_renewal_order_does_not_create_second_open_interval():
    """
    Paying for an already-active CoachStudent link must not open a second
    interval. Only 1 open interval should exist after two payments.
    """
    import uuid
    from unittest.mock import patch

    from purchase_app.models import Order, Plan
    from purchase_app.services import on_payment_success
    from users_app.models import CoachStudentInterval

    coach = make_coach()
    student = make_student(email='renewal@example.com', full_name='Renewal Student')
    plan = baker.make(Plan, duration_days=30, active=True, price_kurus=100_00)

    # First order activates the link and opens an interval
    order1 = baker.make(
        Order,
        email=student.email,
        full_name=student.full_name,
        coach=coach,
        plan=plan,
        amount_kurus=plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
    )
    with patch('django_q.tasks.async_task'):
        on_payment_success(order1)

    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1, 'Expected exactly 1 open interval after first payment'

    # Second order is a renewal — student already active, same coach
    order2 = baker.make(
        Order,
        email=student.email,
        full_name=student.full_name,
        coach=coach,
        plan=plan,
        amount_kurus=plan.price_kurus,
        status=Order.STATUS_PENDING,
        provider='sandbox',
        provider_ref=f'sandbox-{uuid.uuid4()}',
    )
    with patch('django_q.tasks.async_task'):
        on_payment_success(order2)

    open_count = CoachStudentInterval.objects.filter(
        student=student, ended_at__isnull=True
    ).count()
    assert open_count == 1, (
        f'Renewal opened a second interval (found {open_count}). '
        'The `was_inactive` guard in on_payment_success is broken.'
    )


# ── regression: reassign bad target ──────────────────────────────────────────

@pytest.mark.django_db
def test_reassign_bad_target_shows_friendly_error(staff_client):
    """
    Submitting a nonexistent, inactive, unapproved, or non-coach target pk
    must return HTTP 200 with an error message, never a 500.
    """
    client, _ = staff_client
    old_coach = make_coach()
    student = make_student(coach=old_coach)
    link = make_link(old_coach, student)
    open_interval(link)
    url = reverse('panel_koc_degistir', args=[student.pk])

    cases = [
        ('999999999',),  # nonexistent pk
        (str(baker.make(User, role='coach', is_active=False, is_approved=True).pk),),  # inactive
        (str(baker.make(User, role='coach', is_active=True, is_approved=False).pk),),  # unapproved
        (str(baker.make(User, role='student', is_active=True, is_approved=True).pk),),  # not a coach
    ]
    for (target_id,) in cases:
        response = client.post(url, {'new_coach_id': target_id})
        assert response.status_code == 200, (
            f'Expected 200 for bad target {target_id!r}, got {response.status_code}'
        )
        assert response.context.get('error'), (
            f'Expected error message in context for target {target_id!r}'
        )


# ── regression: coach dashboard no writes when all linked ────────────────────

@pytest.mark.django_db
def test_coach_dashboard_get_creates_no_links_or_intervals_when_all_linked():
    """
    When every student on the coach's roster already has an active CoachStudent
    row with an open interval, a plain GET of /coach/ must not create new
    CoachStudent or CoachStudentInterval rows.

    NOTE: CoachAuditLog IS written on every GET (line 2394 in exams_app/views.py
    — `CoachAuditLog.objects.create(coach=..., action='viewed_roster')`). That is
    intentional roster-access logging and is NOT counted here.
    """
    coach = make_coach()
    s1 = make_student(coach=coach)
    s2 = make_student(coach=coach)
    for s in (s1, s2):
        link = make_link(coach, s, active=True)
        open_interval(link)

    c = Client()
    c.force_login(coach)

    cs_before = CoachStudent.objects.count()
    ci_before = CoachStudentInterval.objects.count()

    url = reverse('coach:dashboard')
    response = c.get(url)

    assert response.status_code == 200
    assert CoachStudent.objects.count() == cs_before, (
        'GET /coach/ created unexpected CoachStudent rows even though all students were already linked'
    )
    assert CoachStudentInterval.objects.count() == ci_before, (
        'GET /coach/ created unexpected CoachStudentInterval rows even though all students were already linked'
    )


# ── regression: open_interval idempotency ────────────────────────────────────

@pytest.mark.django_db
def test_open_interval_idempotent_same_coach():
    """Calling open_interval twice for the same (coach, student) creates only one row."""
    coach = make_coach()
    student = make_student()
    link = make_link(coach, student)

    open_interval(link)
    open_interval(link)

    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1


# ── regression: billing-update reactivation ──────────────────────────────────

@pytest.mark.django_db
def test_billing_update_reactivation_on_active_link_creates_no_second_interval():
    """
    POST panel_billing_update on a link that is already active must not open a
    second interval (ensure_active_link is idempotent for active links).
    """
    from django.test import Client as _Client

    staff = baker.make(User, role='coach', is_active=True, is_staff=True)
    coach = make_coach()
    student = make_student(coach=coach)
    link = make_link(coach, student, active=True)
    open_interval(link)

    c = _Client()
    c.force_login(staff)

    import json
    from django.urls import reverse as _reverse
    url = _reverse('panel_billing_update', args=[link.pk])
    payload = {
        'source': 'vagus',
        'next_payment_due': (date.today() + timedelta(days=30)).isoformat(),
    }
    response = c.post(
        url,
        data=json.dumps(payload),
        content_type='application/json',
    )

    assert response.status_code == 200
    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1, 'billing-update on already-active link must not open a second interval'


# ── regression: GET student page writes nothing ───────────────────────────────

@pytest.mark.django_db
def test_coach_student_detail_get_creates_no_links_or_intervals():
    """
    GET /coach/student/<id>/ must not write CoachStudent or CoachStudentInterval
    rows when the student is already properly linked.
    (CoachAuditLog IS written intentionally and is not counted.)
    """
    coach = make_coach()
    student = make_student(coach=coach)
    link = make_link(coach, student, active=True)
    open_interval(link)

    c = Client()
    c.force_login(coach)

    cs_before = CoachStudent.objects.count()
    ci_before = CoachStudentInterval.objects.count()

    url = reverse('coach:student_detail', args=[student.pk])
    response = c.get(url)

    assert response.status_code == 200
    assert CoachStudent.objects.count() == cs_before
    assert CoachStudentInterval.objects.count() == ci_before


# ── consistency command ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_consistency_command_finds_active_no_interval():
    """Kind A: active link without an open interval is detected."""
    from django.core.management import call_command
    from io import StringIO

    coach = make_coach()
    student = make_student()
    make_link(coach, student, active=True)  # no open_interval call

    out = StringIO()
    call_command('check_coach_consistency', stdout=out)
    assert '[A]' in out.getvalue()


@pytest.mark.django_db
def test_consistency_command_finds_interval_no_active():
    """Kind B: open interval without an active link is detected."""
    from django.core.management import call_command
    from io import StringIO

    coach = make_coach()
    student = make_student()
    link = make_link(coach, student, active=False)
    open_interval(link)  # open but link is inactive

    out = StringIO()
    call_command('check_coach_consistency', stdout=out)
    assert '[B]' in out.getvalue()


@pytest.mark.django_db
def test_consistency_command_finds_duplicate_open():
    """Kind C: two open intervals for one student is detected."""
    from django.core.management import call_command
    from django.utils import timezone
    from io import StringIO

    coach = make_coach()
    student = make_student()
    make_link(coach, student, active=True)
    # Force two open intervals directly (bypasses idempotency guard to simulate drift)
    now = timezone.now()
    CoachStudentInterval.objects.create(
        coach_id=coach.pk, student_id=student.pk, source='vagus', started_at=now,
    )
    CoachStudentInterval.objects.create(
        coach_id=coach.pk, student_id=student.pk, source='vagus', started_at=now,
    )

    out = StringIO()
    call_command('check_coach_consistency', stdout=out)
    assert '[C]' in out.getvalue()


@pytest.mark.django_db
def test_consistency_command_finds_coach_fk_no_link():
    """Kind D: User.coach set but no active CoachStudent row."""
    from django.core.management import call_command
    from io import StringIO

    coach = make_coach()
    student = make_student(coach=coach)  # User.coach set, no CoachStudent row

    out = StringIO()
    call_command('check_coach_consistency', stdout=out)
    assert '[D]' in out.getvalue()


@pytest.mark.django_db
def test_consistency_command_finds_coach_fk_mismatch():
    """Kind E: active CoachStudent coach differs from User.coach."""
    from django.core.management import call_command
    from io import StringIO

    coach_a = make_coach()
    coach_b = make_coach()
    student = make_student(coach=coach_a)  # User.coach = coach_a
    link = make_link(coach_b, student, active=True)  # but active link is coach_b
    open_interval(link)

    out = StringIO()
    call_command('check_coach_consistency', stdout=out)
    assert '[E]' in out.getvalue()


@pytest.mark.django_db
def test_consistency_command_fix_repairs_active_no_interval():
    """Kind A --fix: opens the missing interval."""
    from django.core.management import call_command

    coach = make_coach()
    student = make_student()
    make_link(coach, student, active=True)  # no interval

    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 0

    call_command('check_coach_consistency', fix=True)

    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1


@pytest.mark.django_db
def test_consistency_command_fix_repairs_coach_fk_no_link():
    """Kind D --fix: creates the missing CoachStudent row via ensure_active_link."""
    from django.core.management import call_command

    coach = make_coach()
    student = make_student(coach=coach)

    assert not CoachStudent.objects.filter(coach=coach, student=student).exists()

    call_command('check_coach_consistency', fix=True)

    assert CoachStudent.objects.filter(coach=coach, student=student, active=True).exists()
    assert CoachStudentInterval.objects.filter(
        coach=coach, student=student, ended_at__isnull=True
    ).count() == 1


# ── unlinked student not viewable by old coach ────────────────────────────────

@pytest.mark.django_db
def test_unlinked_student_not_viewable_by_old_coach():
    """After unlink_student, coach_can_view_student returns False for the old coach."""
    from users_app.decorators import coach_can_view_student

    coach = make_coach()
    student = make_student(coach=coach)
    link = make_link(coach, student, active=True)
    open_interval(link)

    # Unlink via the coach view (POST)
    c = Client()
    c.force_login(coach)
    url = reverse('coach:unlink_student', args=[student.pk])
    response = c.post(url)
    assert response.status_code == 200

    # Both CoachStudent and User.coach must be cleared
    link.refresh_from_db()
    assert link.active is False
    student.refresh_from_db()
    assert student.coach_id is None

    assert coach_can_view_student(coach, student.pk) is False

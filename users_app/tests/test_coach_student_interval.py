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

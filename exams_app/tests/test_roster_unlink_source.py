"""
Tests: coach can remove only own students; Vagus-assigned students are staff-only.
"""
import json
import pytest
from django.test import Client
from model_bakery import baker

from users_app.models import CoachStudent


# ── 1. Vagus student: no trash control in HTML; endpoint returns 403; link stays active ──

@pytest.mark.django_db
def test_vagus_student_no_trash_and_endpoint_403(settings):
    settings.SELF_PURCHASE_ENABLED = True

    coach = baker.make(
        'users_app.User',
        role='coach', is_active=True, is_approved=True, wordpress_post_id=1001,
    )
    student = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    link = baker.make(
        'users_app.CoachStudent',
        coach=coach, student=student, active=True,
        source=CoachStudent.SOURCE_VAGUS,
    )

    c = Client()
    c.force_login(coach)

    html = c.get('/coach/').content.decode()
    assert 'listeden çıkar' not in html

    resp = c.post(f'/coach/student/{student.id}/unlink/')
    assert resp.status_code == 403
    data = json.loads(resp.content)
    assert data['ok'] is False
    assert 'Vagus' in data['error']

    link.refresh_from_db()
    assert link.active is True


# ── 2. Own student: trash control present in HTML; endpoint deactivates link ──────────────

@pytest.mark.django_db
def test_own_student_has_trash_and_unlink_works(settings):
    settings.SELF_PURCHASE_ENABLED = True

    coach = baker.make(
        'users_app.User',
        role='coach', is_active=True, is_approved=True, wordpress_post_id=1002,
    )
    student = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    link = baker.make(
        'users_app.CoachStudent',
        coach=coach, student=student, active=True,
        source=CoachStudent.SOURCE_COACH,
    )

    c = Client()
    c.force_login(coach)

    html = c.get('/coach/').content.decode()
    assert 'listeden çıkar' in html

    resp = c.post(f'/coach/student/{student.id}/unlink/')
    assert resp.status_code == 200
    assert json.loads(resp.content)['ok'] is True

    link.refresh_from_db()
    assert link.active is False


# ── 3. Staff can unlink a Vagus student via the panel endpoint ───────────────────────────

@pytest.mark.django_db
def test_staff_can_unlink_vagus_student():
    coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    student = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    link = baker.make(
        'users_app.CoachStudent',
        coach=coach, student=student, active=True,
        source=CoachStudent.SOURCE_VAGUS,
    )
    staff = baker.make('users_app.User', is_staff=True, is_active=True)

    c = Client()
    c.force_login(staff)

    resp = c.post(f'/panel/student/{coach.id}/{student.id}/unlink/')
    assert resp.status_code == 200
    assert json.loads(resp.content)['ok'] is True

    link.refresh_from_db()
    assert link.active is False

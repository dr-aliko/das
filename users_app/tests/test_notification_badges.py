"""
Notification badge endpoint tests:
1. student mark-read returns correct unread_count
2. coach mark-all-read (alerts) returns unread_total=0 (when no notifs pending)
3. data-unread-badge attribute is present in the student header
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from model_bakery import baker

from users_app.models import CoachAlert, Notification

User = get_user_model()


@pytest.fixture
def student(db):
    u = baker.make(User, role='student', is_active=True)
    u.set_password('pw')
    u.save()
    return u


@pytest.fixture
def coach(db):
    u = baker.make(User, role='coach', is_active=True, is_approved=True)
    u.set_password('pw')
    u.save()
    return u


@pytest.fixture
def student_client(student):
    c = Client()
    c.login(username=student.email, password='pw')
    return c


@pytest.fixture
def coach_client(coach):
    c = Client()
    c.login(username=coach.email, password='pw')
    return c


@pytest.mark.django_db
def test_student_mark_read_returns_unread_count(student, student_client):
    """POST /student/notifications/<pk>/read/ must return {ok, unread_count} with the real server count."""
    n1 = baker.make(Notification, user=student, is_read=False, hidden_by_user=False)
    n2 = baker.make(Notification, user=student, is_read=False, hidden_by_user=False)

    resp = student_client.post(
        reverse('student_notification_read', kwargs={'pk': n1.pk}),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data['ok'] is True
    assert 'unread_count' in data
    assert data['unread_count'] == 1  # n2 still unread


@pytest.mark.django_db
def test_coach_alert_mark_all_read_returns_zero_when_no_notifs(coach, coach_client):
    """alert_mark_all_read must return unread_total=0 when there are no pending notifications."""
    student = baker.make(User, role='student', is_active=True)
    baker.make(
        CoachAlert,
        coach=coach, student=student,
        is_read=False, is_dismissed=False, expires_at=None,
        severity='warning', alert_type='net_decline',
        fingerprint='fp-test-1',
    )

    resp = coach_client.post(reverse('users_app:alert_mark_all_read'))
    assert resp.status_code == 200
    data = resp.json()
    assert data['ok'] is True
    assert 'unread_total' in data
    assert data['unread_total'] == 0
    assert data['alert_unread'] == 0


@pytest.mark.django_db
def test_student_header_has_badge_attribute(student, student_client):
    """The rendered student shell header must contain data-unread-badge on the bell badge element."""
    resp = student_client.get(reverse('student:dashboard'))
    assert resp.status_code == 200
    assert b'data-unread-badge' in resp.content

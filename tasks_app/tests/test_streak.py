"""
Tests verifying that completing a GorevGrubu task triggers the streak engine.
"""
import pytest
from datetime import date, timedelta, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.urls import reverse
from model_bakery import baker

from tasks_app.models import GorevGrubu


@pytest.fixture
def student(db):
    return baker.make(
        'users_app.User', role='student', is_active=True,
        current_streak=0, last_activity_date=None, longest_streak=0,
    )


def _make_gorev(student, tarih=None):
    return GorevGrubu.objects.create(
        student=student,
        tarih=tarih or date.today(),
        ders_title='Matematik',
        aktivite_tipi='tekrar',
        is_completed=False,
    )


@pytest.mark.django_db
def test_gorev_completion_increments_streak(client, student):
    """Completing a GorevGrubu task via the student endpoint updates the streak."""
    gorev = _make_gorev(student)
    client.force_login(student)
    url = reverse('student_tasks:api-complete', kwargs={'pk': gorev.pk})
    r = client.post(url, content_type='application/json', data='{}')
    assert r.status_code == 200
    student.refresh_from_db()
    assert student.current_streak == 1
    assert student.last_activity_date == date.today()


@pytest.mark.django_db
def test_gorev_undo_does_not_change_streak(client, student):
    """Toggling a completed task back to incomplete does NOT update streak."""
    gorev = GorevGrubu.objects.create(
        student=student, tarih=date.today(), ders_title='Fizik',
        aktivite_tipi='tekrar', is_completed=True,
    )
    client.force_login(student)
    url = reverse('student_tasks:api-complete', kwargs={'pk': gorev.pk})
    r = client.post(url, content_type='application/json', data='{}')
    assert r.status_code == 200
    student.refresh_from_db()
    assert student.current_streak == 0


@pytest.mark.django_db
def test_exam_activity_still_counts(student):
    """Direct record_activity call (simulating exam save) still works."""
    from users_app.services.streak_engine import record_activity
    record_activity(student)
    student.refresh_from_db()
    assert student.current_streak == 1
    assert student.last_activity_date == date.today()


@pytest.mark.django_db
def test_streak_uses_istanbul_date_not_utc():
    """
    record_activity uses timezone.localdate() (Istanbul), not UTC.
    A call at 00:30 Istanbul (= 21:30 UTC of the previous day) must record
    the Istanbul date, not the UTC date.
    """
    student = baker.make(
        'users_app.User', role='student', is_active=True,
        current_streak=0, last_activity_date=None, longest_streak=0,
    )
    # 2024-03-16 00:30 Istanbul = 2024-03-15 21:30 UTC
    istanbul_date = date(2024, 3, 16)

    with patch('users_app.services.streak_engine.timezone') as mock_tz:
        mock_tz.localdate.return_value = istanbul_date
        mock_tz.timedelta = timedelta

        from users_app.services.streak_engine import record_activity
        record_activity(student)

    student.refresh_from_db()
    assert student.last_activity_date == istanbul_date, (
        "Streak date must be the Istanbul local date (2024-03-16), not the UTC date (2024-03-15)"
    )

"""
Tests for the simplified two-state roster status logic.

dusus — ≥2 exams, most-recent net strictly below previous exam net
iyi   — everyone else (no exams, one exam, equal net, improved net)
"""
import pytest
from datetime import date, timedelta
from model_bakery import baker

from exams_app.utils import get_student_status
from exams_app.models import Exam, ExamResult, Subject


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def student(db):
    return baker.make('users_app.User', role='student', is_active=True)


@pytest.fixture
def subject(db):
    return Subject.objects.first() or baker.make('exams_app.Subject', name='Test')


def _make_exam(student, net, days_ago=0, subject=None):
    exam = baker.make(
        'exams_app.Exam',
        student=student,
        exam_date=date.today() - timedelta(days=days_ago),
    )
    if subject is None:
        subject = Subject.objects.first() or baker.make('exams_app.Subject', name='Test')
    baker.make(
        'exams_app.ExamResult',
        exam=exam,
        subject=subject,
        correct_answers=net,
        wrong_answers=0,
        blank_answers=0,
    )
    return exam


# ── get_student_status() unit tests ───────────────────────────────────────────

@pytest.mark.django_db
def test_status_no_exams_is_iyi(student):
    assert get_student_status(student)['status'] == 'iyi'


@pytest.mark.django_db
def test_status_one_exam_is_iyi(student, subject):
    _make_exam(student, net=50, days_ago=0, subject=subject)
    assert get_student_status(student)['status'] == 'iyi'


@pytest.mark.django_db
def test_status_net_increase_is_iyi(student, subject):
    _make_exam(student, net=40, days_ago=5, subject=subject)   # older
    _make_exam(student, net=50, days_ago=0, subject=subject)   # newer, higher
    assert get_student_status(student)['status'] == 'iyi'


@pytest.mark.django_db
def test_status_net_equal_is_iyi(student, subject):
    _make_exam(student, net=50, days_ago=5, subject=subject)
    _make_exam(student, net=50, days_ago=0, subject=subject)
    assert get_student_status(student)['status'] == 'iyi'


@pytest.mark.django_db
def test_status_net_decrease_is_dusus(student, subject):
    _make_exam(student, net=60, days_ago=5, subject=subject)   # older, higher
    _make_exam(student, net=50, days_ago=0, subject=subject)   # newer, lower
    assert get_student_status(student)['status'] == 'dusus'


@pytest.mark.django_db
def test_status_tiny_decrease_is_dusus(student, subject):
    """Any decrease, no matter how small, counts."""
    _make_exam(student, net=50, days_ago=5, subject=subject)
    _make_exam(student, net=49, days_ago=0, subject=subject)
    assert get_student_status(student)['status'] == 'dusus'


# ── roster view: status_counts add up to total ────────────────────────────────

@pytest.fixture
def coach(db):
    return baker.make('users_app.User', role='coach', is_active=True, is_approved=True)


@pytest.fixture
def coach_client(coach):
    from django.test import Client
    c = Client()
    c.force_login(coach)
    return c


def _link(coach, student):
    from users_app.models import CoachStudent
    CoachStudent.objects.get_or_create(coach=coach, student=student, defaults={'active': True})


@pytest.mark.django_db
def test_roster_counts_add_up_to_total(coach, coach_client, subject):
    s1 = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    s2 = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    s3 = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    _link(coach, s1)
    _link(coach, s2)
    _link(coach, s3)

    # s1: decrease → dusus
    _make_exam(s1, net=60, days_ago=5, subject=subject)
    _make_exam(s1, net=50, days_ago=0, subject=subject)
    # s2: increase → iyi
    _make_exam(s2, net=40, days_ago=5, subject=subject)
    _make_exam(s2, net=55, days_ago=0, subject=subject)
    # s3: no exams → iyi

    from django.urls import reverse
    response = coach_client.get(reverse('coach:dashboard'))
    assert response.status_code == 200

    counts = response.context['status_counts']
    total = response.context['total']
    assert counts['iyi'] + counts['dusus'] == total
    assert 'pasif' not in counts
    assert counts['dusus'] == 1
    assert counts['iyi'] == 2

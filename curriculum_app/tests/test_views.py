from datetime import date, timedelta

import pytest
from django.test import Client
from model_bakery import baker

from curriculum_app.models import MacroPlan


def _coach_client(coach):
    c = Client()
    c.force_login(coach)
    return c


@pytest.fixture
def coach(db):
    return baker.make('users_app.User', role='coach', is_active=True, is_approved=True)


@pytest.fixture
def student(db, coach):
    from users_app.models import CoachStudent
    s = baker.make('users_app.User', role='student', is_active=True,
                   tyt_target_date=date.today() + timedelta(days=180))
    CoachStudent.objects.create(coach=coach, student=s, active=True)
    return s


@pytest.mark.django_db
def test_plan_list_requires_coach(student):
    c = Client()
    c.force_login(student)
    r = c.get('/coach/curriculum/')
    assert r.status_code in (302, 403)


@pytest.mark.django_db
def test_plan_list_ok_for_coach(coach):
    r = _coach_client(coach).get('/coach/curriculum/')
    assert r.status_code == 200


@pytest.mark.django_db
def test_create_view_ok(coach):
    r = _coach_client(coach).get('/coach/curriculum/new/')
    assert r.status_code == 200


@pytest.mark.django_db
def test_create_post_generates_plan(coach, student):
    r = _coach_client(coach).post('/coach/curriculum/new/', {
        'student_id': student.id,
        'sinav_tipi': 'TYT',
        'algorithm': 'even',
        'title': 'Test Planı',
    })
    assert r.status_code == 302
    assert MacroPlan.objects.filter(coach=coach, student=student).exists()


@pytest.mark.django_db
def test_detail_view_ok(coach, student):
    plan = MacroPlan.objects.create(
        coach=coach, student=student, sinav_tipi='TYT',
        target_date=date.today() + timedelta(days=180), algorithm='even',
    )
    r = _coach_client(coach).get(f'/coach/curriculum/{plan.pk}/')
    assert r.status_code == 200


@pytest.mark.django_db
def test_detail_view_blocked_for_other_coach(student):
    other_coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    plan = MacroPlan.objects.create(
        coach=other_coach, student=student, sinav_tipi='TYT',
        target_date=date.today() + timedelta(days=180), algorithm='even',
    )
    yet_another_coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    r = _coach_client(yet_another_coach).get(f'/coach/curriculum/{plan.pk}/')
    assert r.status_code == 404


@pytest.mark.django_db
def test_delete_removes_plan(coach, student):
    plan = MacroPlan.objects.create(
        coach=coach, student=student, sinav_tipi='TYT',
        target_date=date.today() + timedelta(days=180), algorithm='even',
    )
    pk = plan.pk
    r = _coach_client(coach).post(f'/coach/curriculum/{pk}/delete/')
    assert r.status_code == 302
    assert not MacroPlan.objects.filter(pk=pk).exists()

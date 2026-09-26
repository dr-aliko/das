import json
from datetime import date, timedelta

import pytest
from django.test import Client
from model_bakery import baker

from tasks_app.models import GorevGrubu
from tasks_app.services import tasks as tasks_svc


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def student(db):
    return baker.make('users_app.User', role='student', is_active=True)


@pytest.fixture
def other_student(db):
    return baker.make('users_app.User', role='student', is_active=True)


def _make_task(student, tarih, is_completed=False, **kwargs):
    return GorevGrubu.objects.create(
        student=student,
        tarih=tarih,
        ders_title='Test Görevi',
        aktivite_tipi='tekrar',
        is_completed=is_completed,
        **kwargs,
    )


# ── Test 1: overdue task appears in geciken list ───────────────────────────────

@pytest.mark.django_db
def test_overdue_task_appears_in_geciken(student):
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)

    result = tasks_svc.geciken_gorevler(student)

    assert len(result) == 1
    assert result[0]['id'] == task.id
    assert result[0]['tarih'] == yesterday.isoformat()


@pytest.mark.django_db
def test_completed_task_not_in_geciken(student):
    yesterday = date.today() - timedelta(days=1)
    _make_task(student, tarih=yesterday, is_completed=True)

    result = tasks_svc.geciken_gorevler(student)
    assert result == []


@pytest.mark.django_db
def test_future_task_not_in_geciken(student):
    tomorrow = date.today() + timedelta(days=1)
    _make_task(student, tarih=tomorrow)

    result = tasks_svc.geciken_gorevler(student)
    assert result == []


@pytest.mark.django_db
def test_todays_task_not_in_geciken(student):
    _make_task(student, tarih=date.today())

    result = tasks_svc.geciken_gorevler(student)
    assert result == []


@pytest.mark.django_db
def test_hidden_task_not_in_geciken(student):
    yesterday = date.today() - timedelta(days=1)
    _make_task(student, tarih=yesterday, is_hidden_by_student=True)

    result = tasks_svc.geciken_gorevler(student)
    assert result == []


# ── Test 2: move_to_today updates fields correctly ────────────────────────────

@pytest.mark.django_db
def test_move_to_today_updates_tarih(student):
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)

    result = tasks_svc.move_to_today(student, task.id)

    task.refresh_from_db()
    assert task.tarih == date.today()
    assert task.original_tarih == yesterday
    assert task.last_moved_at is not None
    assert result is not None
    assert result['tarih'] == date.today().isoformat()
    assert result['original_tarih'] == yesterday.isoformat()


@pytest.mark.django_db
def test_move_to_today_removes_from_geciken(student):
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)

    tasks_svc.move_to_today(student, task.id)

    geciken = tasks_svc.geciken_gorevler(student)
    assert all(g['id'] != task.id for g in geciken)


@pytest.mark.django_db
def test_moved_task_appears_in_todays_week(student):
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)

    tasks_svc.move_to_today(student, task.id)

    from tasks_app.services import week as week_svc
    today = date.today()
    basi, sonu = week_svc.week_bounds(today)
    gorevler = tasks_svc.week_for_own_student(student, basi, sonu)
    assert any(g['id'] == task.id for g in gorevler)


# ── Test 3: original_tarih stays pinned on repeated moves ────────────────────

@pytest.mark.django_db
def test_original_tarih_pinned_on_second_move(student):
    two_days_ago = date.today() - timedelta(days=2)
    task = _make_task(student, tarih=two_days_ago)

    # First move: tarih → today, original_tarih set to two_days_ago
    tasks_svc.move_to_today(student, task.id)
    task.refresh_from_db()
    first_moved_at = task.last_moved_at
    assert task.original_tarih == two_days_ago

    # Simulate next day: push tarih back to yesterday so it's overdue again
    task.tarih = date.today() - timedelta(days=1)
    task.save(update_fields=['tarih'])

    # Second move
    tasks_svc.move_to_today(student, task.id)
    task.refresh_from_db()

    # original_tarih must still point to two_days_ago (first original)
    assert task.original_tarih == two_days_ago
    # last_moved_at was updated
    assert task.last_moved_at > first_moved_at
    # tarih is today again
    assert task.tarih == date.today()


# ── Test 4: completed task shows full trail ────────────────────────────────────

@pytest.mark.django_db
def test_completed_moved_task_has_trail(student):
    from django.utils import timezone
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)

    tasks_svc.move_to_today(student, task.id)
    tasks_svc.toggle_complete(student, task.id)

    task.refresh_from_db()
    assert task.original_tarih == yesterday
    assert task.last_moved_at is not None
    assert task.completed_at is not None
    assert task.is_completed is True


# ── Test 5: never-moved task has no original_tarih ────────────────────────────

@pytest.mark.django_db
def test_never_moved_task_has_no_trail(student):
    task = _make_task(student, tarih=date.today())
    tasks_svc.toggle_complete(student, task.id)

    task.refresh_from_db()
    assert task.original_tarih is None
    assert task.last_moved_at is None
    assert task.is_completed is True


# ── Test 6: ownership — student cannot move another student's task ────────────

@pytest.mark.django_db
def test_move_to_today_rejects_wrong_student(student, other_student):
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)

    result = tasks_svc.move_to_today(other_student, task.id)

    assert result is None
    task.refresh_from_db()
    assert task.tarih == yesterday  # unchanged


# ── Test 6b: ownership via API endpoint ───────────────────────────────────────

@pytest.mark.django_db
def test_bugune_al_api_rejects_wrong_student(student, other_student):
    client = Client()
    client.force_login(other_student)

    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)

    resp = client.post(
        f'/student/tasks/api/gorev/{task.id}/bugune-al',
        data='{}',
        content_type='application/json',
    )
    assert resp.status_code == 404

    task.refresh_from_db()
    assert task.tarih == yesterday  # unchanged


@pytest.mark.django_db
def test_bugune_al_api_succeeds_for_owner(student):
    client = Client()
    client.force_login(student)

    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)

    resp = client.post(
        f'/student/tasks/api/gorev/{task.id}/bugune-al',
        data='{}',
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data['ok'] is True
    assert data['gorev']['tarih'] == date.today().isoformat()


@pytest.mark.django_db
def test_geciken_api_requires_login():
    client = Client()
    resp = client.get('/student/tasks/api/geciken')
    assert resp.status_code in (302, 403)

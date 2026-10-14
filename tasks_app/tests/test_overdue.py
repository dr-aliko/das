import json
import re
from datetime import date, timedelta
from pathlib import Path

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
def test_older_task_not_in_geciken(student):
    three_days_ago = date.today() - timedelta(days=3)
    _make_task(student, tarih=three_days_ago)

    result = tasks_svc.geciken_gorevler(student)
    assert result == []


@pytest.mark.django_db
def test_two_days_ago_task_not_in_geciken(student):
    two_days_ago = date.today() - timedelta(days=2)
    _make_task(student, tarih=two_days_ago)

    result = tasks_svc.geciken_gorevler(student)
    assert result == []


@pytest.mark.django_db
def test_older_task_still_in_weekly_view(student):
    three_days_ago = date.today() - timedelta(days=3)
    task = _make_task(student, tarih=three_days_ago)

    from tasks_app.services import week as week_svc
    basi, sonu = week_svc.week_bounds(three_days_ago)
    gorevler = tasks_svc.week_for_own_student(student, basi, sonu)
    assert any(g['id'] == task.id for g in gorevler)


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
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)

    # Day 1: task appears in tray (tarih=yesterday). Student moves it to today.
    tasks_svc.move_to_today(student, task.id)
    task.refresh_from_db()
    first_moved_at = task.last_moved_at
    assert task.original_tarih == yesterday
    assert task.tarih == date.today()

    # Simulate next day passing without completion: push tarih back to yesterday
    # (equivalent to tarih now being "yesterday" from tomorrow's perspective).
    task.tarih = date.today() - timedelta(days=1)
    task.save(update_fields=['tarih'])

    # Day 2: task reappears in tray. Student moves it to today again.
    tasks_svc.move_to_today(student, task.id)
    task.refresh_from_db()

    # original_tarih must still point to the FIRST original date, not the intermediate one
    assert task.original_tarih == yesterday
    assert task.last_moved_at > first_moved_at
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


# ── Test 7: indicator data reaches weekly view serialization ──────────────────
# NOTE: Alpine x-if is evaluated client-side only. Django's test client returns
# the static template markup (which always contains the x-if binding). The tests
# below verify the DATA CONTRACT (API JSON contains original_tarih) and that the
# BINDING TEXT exists in the template source. Whether the chip actually appears
# in the DOM is unverified without a browser.

@pytest.mark.django_db
def test_moved_task_serialized_has_original_tarih(student):
    """Service layer: a moved task includes original_tarih in its serialized output."""
    from tasks_app.services import week as week_svc
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)
    tasks_svc.move_to_today(student, task.id)

    today = date.today()
    basi, sonu = week_svc.week_bounds(today)
    gorevler = tasks_svc.week_for_own_student(student, basi, sonu)
    moved = next(g for g in gorevler if g['id'] == task.id)
    assert moved['original_tarih'] == yesterday.isoformat()


@pytest.mark.django_db
def test_never_moved_task_serialized_no_original_tarih(student):
    """Service layer: a never-moved task has original_tarih=None in its serialized output."""
    from tasks_app.services import week as week_svc
    task = _make_task(student, tarih=date.today())

    today = date.today()
    basi, sonu = week_svc.week_bounds(today)
    gorevler = tasks_svc.week_for_own_student(student, basi, sonu)
    g = next(g for g in gorevler if g['id'] == task.id)
    assert g['original_tarih'] is None


# ── Test 8: student API endpoint returns original_tarih field ─────────────────

@pytest.mark.django_db
def test_student_api_moved_task_has_original_tarih(student):
    """Student week API: moved task has original_tarih in JSON response."""
    client = Client()
    client.force_login(student)
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(student, tarih=yesterday)
    tasks_svc.move_to_today(student, task.id)

    resp = client.get(f'/student/tasks/api/gorevler?hafta={date.today().isoformat()}')
    assert resp.status_code == 200
    gorevler = resp.json()['gorevler']
    moved = next(g for g in gorevler if g['id'] == task.id)
    assert moved['original_tarih'] == yesterday.isoformat()


@pytest.mark.django_db
def test_student_api_unmoved_task_no_original_tarih(student):
    """Student week API: never-moved task has original_tarih=null in JSON response."""
    client = Client()
    client.force_login(student)
    _make_task(student, tarih=date.today())

    resp = client.get(f'/student/tasks/api/gorevler?hafta={date.today().isoformat()}')
    assert resp.status_code == 200
    gorevler = resp.json()['gorevler']
    assert all(g['original_tarih'] is None for g in gorevler)


# ── Test 9: coach API endpoint returns original_tarih field ───────────────────

@pytest.fixture
def coach(db):
    return baker.make('users_app.User', role='coach', is_active=True, is_approved=True)


@pytest.fixture
def coached_student(db, coach):
    return baker.make('users_app.User', role='student', is_active=True, coach=coach)


@pytest.mark.django_db
def test_coach_api_moved_task_has_original_tarih(coach, coached_student):
    """Coach week API: moved task has original_tarih in JSON response."""
    client = Client()
    client.force_login(coach)
    yesterday = date.today() - timedelta(days=1)
    task = _make_task(coached_student, tarih=yesterday)
    tasks_svc.move_to_today(coached_student, task.id)

    resp = client.get(
        f'/coach/tasks/api/gorevler?student_id={coached_student.id}&hafta={date.today().isoformat()}'
    )
    assert resp.status_code == 200
    gorevler = resp.json()['gorevler']
    moved = next(g for g in gorevler if g['id'] == task.id)
    assert moved['original_tarih'] == yesterday.isoformat()


@pytest.mark.django_db
def test_coach_api_unmoved_task_no_original_tarih(coach, coached_student):
    """Coach week API: never-moved task has original_tarih=null in JSON response."""
    client = Client()
    client.force_login(coach)
    _make_task(coached_student, tarih=date.today())

    resp = client.get(
        f'/coach/tasks/api/gorevler?student_id={coached_student.id}&hafta={date.today().isoformat()}'
    )
    assert resp.status_code == 200
    gorevler = resp.json()['gorevler']
    assert all(g['original_tarih'] is None for g in gorevler)


# ── Test 10: source-level template chip audit ─────────────────────────────────
# Static analysis: verify chip condition fields and absence of nested guards.

BASE = Path(__file__).resolve().parent.parent.parent  # repo root


def _src(rel):
    return (BASE / rel).read_text(encoding='utf-8')


def test_student_desktop_chip_uses_g_original_tarih():
    """Desktop grid card chip condition: g.original_tarih, text Ertelendi present."""
    src = _src('templates/student/tasks/hafta.html')
    assert 'x-if="g.original_tarih"' in src
    chip_blocks = re.findall(r'x-if="g\.original_tarih"[\s\S]{0,1500}?Ertelendi', src)
    assert len(chip_blocks) >= 1, 'desktop chip with text Ertelendi not found'


def test_student_mobile_chip_uses_raw_original_tarih():
    """Mobile active card chip condition: task.raw?.original_tarih."""
    src = _src('templates/student/tasks/hafta.html')
    assert 'x-if="task.raw?.original_tarih"' in src
    chip_blocks = re.findall(r'x-if="task\.raw\?\.original_tarih"[\s\S]{0,1500}?Ertelendi', src)
    assert len(chip_blocks) >= 1, 'mobile active-card chip with text Ertelendi not found'


def test_completed_accordion_chip_uses_raw_original_tarih():
    """Accordion chip condition: task.raw.original_tarih — field exists in serialized task."""
    src = _src('templates/tasks/partials/_completed_tasks_accordion.html')
    assert 'x-if="task.raw.original_tarih"' in src
    chip_blocks = re.findall(r'x-if="task\.raw\.original_tarih"[\s\S]{0,1500}?Ertelendi', src)
    assert len(chip_blocks) >= 1, 'accordion chip with text Ertelendi not found'


def test_accordion_chip_not_nested_under_other_condition():
    """Accordion chip must not be inside any x-if/x-show other than original_tarih."""
    src = _src('templates/tasks/partials/_completed_tasks_accordion.html')
    match = re.search(r'x-if="task\.raw\.original_tarih"([\s\S]{0,1500}?)Ertelendi', src)
    assert match, 'chip block not found in accordion'
    interior = match.group(1)
    assert 'x-if=' not in interior
    assert 'x-show=' not in interior


def test_student_detail_sheet_chip_uses_raw_original_tarih():
    """Detail sheet chip condition: detailTask?.raw?.original_tarih."""
    src = _src('templates/tasks/partials/_student_task_detail_sheet.html')
    assert 'x-if="detailTask?.raw?.original_tarih"' in src
    chip_blocks = re.findall(r'x-if="detailTask\?\.raw\?\.original_tarih"[\s\S]{0,1500}?Ertelendi', src)
    assert len(chip_blocks) >= 1, 'detail sheet chip with text Ertelendi not found'


def test_coach_desktop_chip_uses_g_original_tarih():
    """Coach desktop grid card chip: g.original_tarih, text Ertelendi present."""
    src = _src('templates/coach/tasks/hafta.html')
    assert 'x-if="g.original_tarih"' in src
    chip_blocks = re.findall(r'x-if="g\.original_tarih"[\s\S]{0,1500}?Ertelendi', src)
    assert len(chip_blocks) >= 1, 'coach desktop chip with text Ertelendi not found'


def test_coach_mobile_chip_uses_raw_original_tarih():
    """Coach mobile active card chip: task.raw?.original_tarih."""
    src = _src('templates/coach/tasks/hafta.html')
    assert 'x-if="task.raw?.original_tarih"' in src
    chip_blocks = re.findall(r'x-if="task\.raw\?\.original_tarih"[\s\S]{0,1500}?Ertelendi', src)
    assert len(chip_blocks) >= 1, 'coach mobile active-card chip with text Ertelendi not found'

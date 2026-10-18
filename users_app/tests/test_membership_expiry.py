"""
Tests for the membership expiry feature:
- membership_expiry_info() wording and day-boundary logic
- is_student_program_expired() helper
- Coach-side 403 for expired Vagus students
- Coach-source and null-source students never blocked
- Student-side operations unaffected
- Renewal lifts block
- AUTO_DEACTIVATE_VAGUS_OVERDUE=False skips the task
"""
import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.test import Client
from model_bakery import baker

from users_app.models import CoachStudent
from users_app.utils import is_student_program_expired, membership_expiry_info


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def coach(db):
    return baker.make('users_app.User', role='coach', is_active=True, is_approved=True)


@pytest.fixture
def student(db):
    return baker.make('users_app.User', role='student', is_active=True)


@pytest.fixture
def vagus_link(coach, student):
    return CoachStudent.objects.create(
        coach=coach,
        student=student,
        source=CoachStudent.SOURCE_VAGUS,
        active=True,
    )


# ── membership_expiry_info() ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_expiry_info_more_than_7_days(vagus_link):
    vagus_link.next_payment_due = date.today() + timedelta(days=30)
    vagus_link.save()
    info = membership_expiry_info(vagus_link)
    assert info is not None
    assert info['variant'] == 'normal'
    assert '30 gün kaldı' == info['label']
    assert info['expired'] is False


@pytest.mark.django_db
def test_expiry_info_warning_7_days(vagus_link):
    vagus_link.next_payment_due = date.today() + timedelta(days=7)
    vagus_link.save()
    info = membership_expiry_info(vagus_link)
    assert info['variant'] == 'warning'
    assert '7 gün kaldı' == info['label']
    assert info['expired'] is False


@pytest.mark.django_db
def test_expiry_info_warning_1_day(vagus_link):
    vagus_link.next_payment_due = date.today() + timedelta(days=1)
    vagus_link.save()
    info = membership_expiry_info(vagus_link)
    assert info['variant'] == 'warning'
    assert '1 gün kaldı' == info['label']
    assert info['expired'] is False


@pytest.mark.django_db
def test_expiry_info_today(vagus_link):
    vagus_link.next_payment_due = date.today()
    vagus_link.save()
    info = membership_expiry_info(vagus_link)
    assert info['variant'] == 'warning'
    assert info['label'] == 'Bugün bitiyor'
    assert info['expired'] is False


@pytest.mark.django_db
def test_expiry_info_expired_yesterday(vagus_link):
    vagus_link.next_payment_due = date.today() - timedelta(days=1)
    vagus_link.save()
    info = membership_expiry_info(vagus_link)
    assert info['variant'] == 'expired'
    assert 'Süre bitti (1 gün önce)' == info['label']
    assert info['expired'] is True


@pytest.mark.django_db
def test_expiry_info_expired_many_days(vagus_link):
    vagus_link.next_payment_due = date.today() - timedelta(days=15)
    vagus_link.save()
    info = membership_expiry_info(vagus_link)
    assert info['variant'] == 'expired'
    assert '15 gün önce' in info['label']


@pytest.mark.django_db
def test_expiry_info_coach_source_returns_none(coach, student):
    cs = CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_COACH, active=True,
        next_payment_due=date.today() - timedelta(days=5),
    )
    assert membership_expiry_info(cs) is None


@pytest.mark.django_db
def test_expiry_info_null_source_returns_none(coach, student):
    cs = CoachStudent.objects.create(
        coach=coach, student=student,
        source=None, active=True,
        next_payment_due=date.today() - timedelta(days=5),
    )
    assert membership_expiry_info(cs) is None


@pytest.mark.django_db
def test_expiry_info_no_due_date_returns_none(vagus_link):
    vagus_link.next_payment_due = None
    vagus_link.save()
    assert membership_expiry_info(vagus_link) is None


# ── is_student_program_expired() ─────────────────────────────────────────────

@pytest.mark.django_db
def test_expired_vagus_student_returns_true(coach, student, vagus_link):
    vagus_link.next_payment_due = date.today() - timedelta(days=1)
    vagus_link.save()
    assert is_student_program_expired(coach, student.id) is True


@pytest.mark.django_db
def test_non_expired_vagus_student_returns_false(coach, student, vagus_link):
    vagus_link.next_payment_due = date.today() + timedelta(days=10)
    vagus_link.save()
    assert is_student_program_expired(coach, student.id) is False


@pytest.mark.django_db
def test_due_today_is_not_expired(coach, student, vagus_link):
    vagus_link.next_payment_due = date.today()
    vagus_link.save()
    assert is_student_program_expired(coach, student.id) is False


@pytest.mark.django_db
def test_coach_source_never_expired(coach, student):
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_COACH, active=True,
        next_payment_due=date.today() - timedelta(days=30),
    )
    assert is_student_program_expired(coach, student.id) is False


@pytest.mark.django_db
def test_null_source_never_expired(coach, student):
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=None, active=True,
        next_payment_due=date.today() - timedelta(days=30),
    )
    assert is_student_program_expired(coach, student.id) is False


@pytest.mark.django_db
def test_no_coach_student_record_returns_false(coach, student):
    assert is_student_program_expired(coach, student.id) is False


@pytest.mark.django_db
def test_inactive_link_returns_false(coach, student):
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_VAGUS, active=False,
        next_payment_due=date.today() - timedelta(days=5),
    )
    assert is_student_program_expired(coach, student.id) is False


@pytest.mark.django_db
def test_renewal_lifts_expiry(coach, student, vagus_link):
    vagus_link.next_payment_due = date.today() - timedelta(days=5)
    vagus_link.save()
    assert is_student_program_expired(coach, student.id) is True
    vagus_link.next_payment_due = date.today() + timedelta(days=30)
    vagus_link.save()
    assert is_student_program_expired(coach, student.id) is False


# ── Tasks endpoint — GorevListView.post (create) ──────────────────────────────

@pytest.mark.django_db
def test_create_task_blocked_for_expired_vagus(coach, student, vagus_link):
    vagus_link.next_payment_due = date.today() - timedelta(days=1)
    vagus_link.save()
    student.coach = coach
    student.save(update_fields=['coach'])
    c = Client()
    c.force_login(coach)
    payload = {
        'student_id': student.id,
        'tarih': str(date.today()),
        'aktivite_tipi': 'soru_cozumu',
        'ders_title': 'Test',
        'ozel_sure_dk': '',
        'detaylar': json.dumps([{'aciklama': 'x', 'sure_bilgisi': ''}]),
    }
    resp = c.post(
        '/coach/tasks/api/gorevler',
        data=json.dumps(payload),
        content_type='application/json',
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_task_allowed_for_valid_vagus(coach, student, vagus_link):
    vagus_link.next_payment_due = date.today() + timedelta(days=30)
    vagus_link.save()
    student.coach = coach
    student.save(update_fields=['coach'])
    c = Client()
    c.force_login(coach)
    payload = {
        'student_id': student.id,
        'tarih': str(date.today()),
        'aktivite_tipi': 'soru_cozumu',
        'ders_title': 'Test',
        'ozel_sure_dk': '',
        'detaylar': json.dumps([{'aciklama': 'x', 'sure_bilgisi': ''}]),
    }
    resp = c.post(
        '/coach/tasks/api/gorevler',
        data=json.dumps(payload),
        content_type='application/json',
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_create_task_allowed_for_coach_source(coach, student):
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_COACH, active=True,
        next_payment_due=date.today() - timedelta(days=5),
    )
    student.coach = coach
    student.save(update_fields=['coach'])
    c = Client()
    c.force_login(coach)
    payload = {
        'student_id': student.id,
        'tarih': str(date.today()),
        'aktivite_tipi': 'soru_cozumu',
        'ders_title': 'Test',
        'ozel_sure_dk': '',
        'detaylar': json.dumps([{'aciklama': 'x', 'sure_bilgisi': ''}]),
    }
    resp = c.post(
        '/coach/tasks/api/gorevler',
        data=json.dumps(payload),
        content_type='application/json',
    )
    assert resp.status_code == 201


# ── Tasks endpoint — GorevDetailView.put/delete ────────────────────────────────

@pytest.mark.django_db
def test_edit_task_blocked_for_expired_vagus(coach, student, vagus_link):
    from tasks_app.models import GorevGrubu
    vagus_link.next_payment_due = date.today() - timedelta(days=1)
    vagus_link.save()
    student.coach = coach
    student.save(update_fields=['coach'])
    grup = GorevGrubu.objects.create(
        student=student, tarih=date.today(),
        ders_title='Test', aktivite_tipi='soru_cozumu',
    )
    c = Client()
    c.force_login(coach)
    payload = {
        'tarih': str(date.today()),
        'aktivite_tipi': 'soru_cozumu',
        'ders_title': 'Updated',
        'ozel_sure_dk': '',
        'detaylar': json.dumps([{'aciklama': 'y', 'sure_bilgisi': ''}]),
    }
    resp = c.put(
        f'/coach/tasks/api/gorev/{grup.id}',
        data=json.dumps(payload),
        content_type='application/json',
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_delete_task_blocked_for_expired_vagus(coach, student, vagus_link):
    from tasks_app.models import GorevGrubu
    vagus_link.next_payment_due = date.today() - timedelta(days=1)
    vagus_link.save()
    student.coach = coach
    student.save(update_fields=['coach'])
    grup = GorevGrubu.objects.create(
        student=student, tarih=date.today(),
        ders_title='Test', aktivite_tipi='soru_cozumu',
    )
    c = Client()
    c.force_login(coach)
    resp = c.delete(f'/coach/tasks/api/gorev/{grup.id}')
    assert resp.status_code == 403


# ── Another coach's student must not be exposed ───────────────────────────────

@pytest.mark.django_db
def test_another_coaches_student_not_blocked_by_expiry(coach, student):
    other_coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    CoachStudent.objects.create(
        coach=other_coach, student=student,
        source=CoachStudent.SOURCE_VAGUS, active=True,
        next_payment_due=date.today() - timedelta(days=5),
    )
    # This coach has no link to student — is_student_program_expired should return False
    assert is_student_program_expired(coach, student.id) is False


# ── Student-side operations unaffected by expiry ─────────────────────────────

@pytest.mark.django_db
def test_student_can_complete_task_when_expired(coach, student, vagus_link):
    from tasks_app.models import GorevGrubu
    vagus_link.next_payment_due = date.today() - timedelta(days=5)
    vagus_link.save()
    student.coach = coach
    student.save(update_fields=['coach'])
    grup = GorevGrubu.objects.create(
        student=student, tarih=date.today(),
        ders_title='Test', aktivite_tipi='soru_cozumu',
    )
    c = Client()
    c.force_login(student)
    resp = c.post(
        f'/student/tasks/api/complete/{grup.id}',
        data=json.dumps({'time_spent_dk': 30}),
        content_type='application/json',
    )
    assert resp.status_code == 200
    grup.refresh_from_db()
    assert grup.is_completed is True


# ── auto_deactivate_overdue_vagus_students gating ─────────────────────────────

# ── Additional is_student_program_expired() coverage ─────────────────────────

@pytest.mark.django_db
def test_vagus_null_date_not_expired(coach, student):
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_VAGUS, active=True,
        next_payment_due=None,
    )
    assert is_student_program_expired(coach, student.id) is False


@pytest.mark.django_db
def test_is_expired_fails_open_on_unexpected_exception(coach, student):
    """An exception other than DoesNotExist must return False (fail open), not propagate."""
    from unittest.mock import patch as _patch
    from users_app.models import CoachStudent as _CS
    with _patch.object(_CS.objects, 'get', side_effect=RuntimeError('simulated db failure')):
        result = is_student_program_expired(coach, student.id)
    assert result is False


# ── Create endpoint — additional allowed cases ────────────────────────────────

def _create_payload(student_id):
    return {
        'student_id': student_id,
        'tarih': str(date.today()),
        'aktivite_tipi': 'soru_cozumu',
        'ders_title': 'Test',
        'ozel_sure_dk': '',
        'detaylar': json.dumps([{'aciklama': 'x', 'sure_bilgisi': ''}]),
    }


@pytest.mark.django_db
def test_create_task_allowed_null_source_past_date(coach, student):
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=None, active=True,
        next_payment_due=date.today() - timedelta(days=5),
    )
    student.coach = coach
    student.save(update_fields=['coach'])
    c = Client()
    c.force_login(coach)
    resp = c.post(
        '/coach/tasks/api/gorevler',
        data=json.dumps(_create_payload(student.id)),
        content_type='application/json',
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_create_task_allowed_vagus_null_date(coach, student):
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_VAGUS, active=True,
        next_payment_due=None,
    )
    student.coach = coach
    student.save(update_fields=['coach'])
    c = Client()
    c.force_login(coach)
    resp = c.post(
        '/coach/tasks/api/gorevler',
        data=json.dumps(_create_payload(student.id)),
        content_type='application/json',
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_create_task_allowed_inactive_vagus_link(coach, student):
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_VAGUS, active=False,
        next_payment_due=date.today() - timedelta(days=5),
    )
    student.coach = coach
    student.save(update_fields=['coach'])
    c = Client()
    c.force_login(coach)
    resp = c.post(
        '/coach/tasks/api/gorevler',
        data=json.dumps(_create_payload(student.id)),
        content_type='application/json',
    )
    assert resp.status_code == 201


@pytest.mark.django_db
def test_create_task_allowed_no_cs_record(coach, student):
    """No CoachStudent row at all — only User.coach link."""
    student.coach = coach
    student.save(update_fields=['coach'])
    c = Client()
    c.force_login(coach)
    resp = c.post(
        '/coach/tasks/api/gorevler',
        data=json.dumps(_create_payload(student.id)),
        content_type='application/json',
    )
    assert resp.status_code == 201


# ── Edit / delete endpoints — additional allowed cases ────────────────────────

def _edit_payload():
    return {
        'tarih': str(date.today()),
        'aktivite_tipi': 'soru_cozumu',
        'ders_title': 'Updated',
        'ozel_sure_dk': '',
        'detaylar': json.dumps([{'aciklama': 'y', 'sure_bilgisi': ''}]),
    }


@pytest.mark.django_db
def test_edit_task_allowed_coach_source_past_date(coach, student):
    from tasks_app.models import GorevGrubu
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_COACH, active=True,
        next_payment_due=date.today() - timedelta(days=5),
    )
    student.coach = coach
    student.save(update_fields=['coach'])
    grup = GorevGrubu.objects.create(
        student=student, tarih=date.today(),
        ders_title='Test', aktivite_tipi='soru_cozumu',
    )
    c = Client()
    c.force_login(coach)
    resp = c.put(
        f'/coach/tasks/api/gorev/{grup.id}',
        data=json.dumps(_edit_payload()),
        content_type='application/json',
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_edit_task_allowed_vagus_null_date(coach, student):
    from tasks_app.models import GorevGrubu
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_VAGUS, active=True,
        next_payment_due=None,
    )
    student.coach = coach
    student.save(update_fields=['coach'])
    grup = GorevGrubu.objects.create(
        student=student, tarih=date.today(),
        ders_title='Test', aktivite_tipi='soru_cozumu',
    )
    c = Client()
    c.force_login(coach)
    resp = c.put(
        f'/coach/tasks/api/gorev/{grup.id}',
        data=json.dumps(_edit_payload()),
        content_type='application/json',
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_delete_task_allowed_coach_source_past_date(coach, student):
    from tasks_app.models import GorevGrubu
    CoachStudent.objects.create(
        coach=coach, student=student,
        source=CoachStudent.SOURCE_COACH, active=True,
        next_payment_due=date.today() - timedelta(days=5),
    )
    student.coach = coach
    student.save(update_fields=['coach'])
    grup = GorevGrubu.objects.create(
        student=student, tarih=date.today(),
        ders_title='Test', aktivite_tipi='soru_cozumu',
    )
    c = Client()
    c.force_login(coach)
    resp = c.delete(f'/coach/tasks/api/gorev/{grup.id}')
    assert resp.status_code == 200


# ── HaftaView page rendering — wrong-variable and json_script regressions ──────

@pytest.mark.django_db
def test_hafta_page_no_selectedStudent_in_desktop_component(coach):
    """
    Regression for line 591: the bottom-sheet edit/delete div inside panel() (desktop)
    had x-show referencing selectedStudent?.id.  selectedStudent is not in panel()'s
    scope, so Alpine throws ReferenceError and hides the buttons for every student.

    The test splits the rendered HTML at the x-data="panel()" boundary and asserts
    that no _STUDENT_EXPIRY_MAP lookup in the desktop section references selectedStudent.
    Fails on unpatched code, passes after the fix.
    """
    c = Client()
    c.force_login(coach)
    resp = c.get('/coach/tasks/')
    assert resp.status_code == 200
    html = resp.content.decode()

    # Locate the boundary between mobile (coachMobilePanel) and desktop (panel) sections
    desktop_start = html.find('x-data="panel()"')
    assert desktop_start != -1, "Could not find x-data=\"panel()\" in rendered page"

    desktop_html = html[desktop_start:]

    # No expiry-map lookup in the desktop section may reference selectedStudent
    assert 'window._STUDENT_EXPIRY_MAP[selectedStudent' not in desktop_html, (
        "Found window._STUDENT_EXPIRY_MAP[selectedStudent...] inside panel() (desktop): "
        "selectedStudent is not defined in panel()'s scope → ReferenceError → buttons hidden"
    )


@pytest.mark.django_db
def test_hafta_page_expiry_data_not_html_escaped(coach):
    """
    Regression for 9c42773: {{ student_expiry_map_json }} in a <script> tag causes
    Django auto-escaping to turn every " into &quot;, producing a JS SyntaxError
    ({&quot;5&quot;: false}) that leaves _STUDENT_EXPIRY_MAP undefined for every
    student on the page.  Triggered by ANY vagus student with a non-null
    next_payment_due — including paying students with a future date.
    Fix: render the dict through json_script so quotes are never HTML-escaped.
    """
    import json as _json
    import re

    past = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    future = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    coach_src = baker.make('users_app.User', role='student', is_active=True, coach=coach)

    CoachStudent.objects.create(
        coach=coach, student=past,
        source=CoachStudent.SOURCE_VAGUS, active=True,
        next_payment_due=date.today() - timedelta(days=5),
    )
    CoachStudent.objects.create(
        coach=coach, student=future,
        source=CoachStudent.SOURCE_VAGUS, active=True,
        next_payment_due=date.today() + timedelta(days=30),
    )
    CoachStudent.objects.create(
        coach=coach, student=coach_src,
        source=CoachStudent.SOURCE_COACH, active=True,
        next_payment_due=date.today() - timedelta(days=5),
    )

    c = Client()
    c.force_login(coach)
    resp = c.get('/coach/tasks/')
    assert resp.status_code == 200
    html = resp.content.decode()

    # json_script element must be present — fails on 9c42773 which uses a raw <script> tag
    assert 'id="_das_expiry_data"' in html, \
        "json_script element missing — old code used {{ var }} which HTML-escapes the JSON"

    # Extract the element text and confirm no HTML entities snuck in
    m = re.search(
        r'<script[^>]+id=["\']_das_expiry_data["\'][^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    assert m is not None, "Could not locate <script id=_das_expiry_data> in rendered page"
    body = m.group(1)
    assert '&quot;' not in body, \
        "HTML entity &quot; found inside json_script element — double-escaping bug"

    # Content must be parseable JSON
    data = _json.loads(body)

    # Only the expired vagus student must be in the map, with value True
    str_past = str(past.id)
    assert str_past in data, "Expired vagus student must appear in expiry map"
    assert data[str_past] is True

    # Non-expired vagus and coach-source students must NOT be in the map at all
    assert str(future.id) not in data, "Non-expired vagus student must not be in expiry map"
    assert str(coach_src.id) not in data, "Coach-source student must not be in expiry map"


# ── auto_deactivate_overdue_vagus_students gating ─────────────────────────────

@pytest.mark.django_db
def test_auto_deactivate_skipped_when_setting_false(coach, student, vagus_link):
    vagus_link.next_payment_due = date.today() - timedelta(days=5)
    vagus_link.save()
    from users_app.tasks import auto_deactivate_overdue_vagus_students
    with patch('django.conf.settings.AUTO_DEACTIVATE_VAGUS_OVERDUE', False):
        result = auto_deactivate_overdue_vagus_students()
    assert result == 0
    vagus_link.refresh_from_db()
    assert vagus_link.active is True  # not deactivated


@pytest.mark.django_db
def test_auto_deactivate_runs_when_setting_true(coach, student, vagus_link):
    vagus_link.next_payment_due = date.today() - timedelta(days=5)
    vagus_link.save()
    from users_app.tasks import auto_deactivate_overdue_vagus_students
    with patch('django.conf.settings.AUTO_DEACTIVATE_VAGUS_OVERDUE', True):
        with patch('users_app.services.notifications.send_push_notification'):
            result = auto_deactivate_overdue_vagus_students()
    assert result == 1
    vagus_link.refresh_from_db()
    assert vagus_link.active is False

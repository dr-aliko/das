"""
Tests for note + video preservation when copying/editing coach tasks.

Contract verified:
- copy_to_date preserves note, videos, meta, duration on the new copy
- copy_to_date leaves the original task fully intact on the original day
- update() preserves the note when detaylar payload includes the note row
- expired student → 403 on copy endpoint
"""
import json
from datetime import date, timedelta

import pytest
from django.test import Client
from model_bakery import baker

from tasks_app.models import GorevGrubu, GrupDetay
from tasks_app.services import tasks as tasks_svc


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def coach(db):
    return baker.make('users_app.User', role='coach', is_active=True, is_approved=True)


@pytest.fixture
def student(db, coach):
    return baker.make('users_app.User', role='student', is_active=True, coach=coach)


def _make_konu_task_with_videos_and_note(student, tarih):
    """Creates a konu_anlatimi group with two video detaylar and one note detay."""
    meta = {
        "source": "youtube",
        "youtube_playlist_pk": 99,
        "sinav_tipi": "TYT",
        "liste_baslik": "Test Listesi",
        "videos": [
            {"id": 1, "title": "Video 1", "duration": 30},
            {"id": 2, "title": "Video 2", "duration": 20},
        ],
    }
    grup = GorevGrubu.objects.create(
        student=student,
        tarih=tarih,
        aktivite_tipi="konu_anlatimi",
        ders_title="Matematik - Konu Anlatimi",
        ozel_sure_dk=50,
        sira_no=1,
        meta=meta,
    )
    GrupDetay.objects.create(grup=grup, aciklama="Video 1", sure_bilgisi="30 dk")
    GrupDetay.objects.create(grup=grup, aciklama="Video 2", sure_bilgisi="20 dk")
    GrupDetay.objects.create(grup=grup, aciklama="bu konuya dikkat et", sure_bilgisi="")
    return grup


# ── Test 1: copy preserves note, videos, meta, duration on the target day ─────

@pytest.mark.django_db
def test_copy_konu_anlatimi_preserves_note_on_target_day(coach, student):
    monday = date.today()
    tuesday = monday + timedelta(days=1)

    grup = _make_konu_task_with_videos_and_note(student, monday)
    original_meta = dict(grup.meta)

    yeni = tasks_svc.copy_to_date(coach, grup.id, tuesday)

    assert yeni is not None
    assert yeni.tarih == tuesday
    assert yeni.meta == original_meta
    assert yeni.ozel_sure_dk == grup.ozel_sure_dk

    detaylar = list(yeni.detaylar.values("aciklama", "sure_bilgisi"))
    assert len(detaylar) == 3
    note_rows = [d for d in detaylar if not d["sure_bilgisi"]]
    assert len(note_rows) == 1
    assert note_rows[0]["aciklama"] == "bu konuya dikkat et"
    video_rows = [d for d in detaylar if d["sure_bilgisi"]]
    assert len(video_rows) == 2


# ── Test 2: copy leaves the original task fully intact on the original day ────

@pytest.mark.django_db
def test_copy_konu_anlatimi_original_task_unmodified(coach, student):
    monday = date.today()
    tuesday = monday + timedelta(days=1)

    grup = _make_konu_task_with_videos_and_note(student, monday)

    tasks_svc.copy_to_date(coach, grup.id, tuesday)

    # Both days now have a task
    assert GorevGrubu.objects.filter(student=student, tarih=monday).count() == 1
    assert GorevGrubu.objects.filter(student=student, tarih=tuesday).count() == 1

    # Original task unchanged on monday
    grup.refresh_from_db()
    assert grup.tarih == monday
    original_detaylar = list(grup.detaylar.values("aciklama", "sure_bilgisi"))
    assert len(original_detaylar) == 3
    note_rows = [d for d in original_detaylar if not d["sure_bilgisi"]]
    assert note_rows[0]["aciklama"] == "bu konuya dikkat et"


# ── Test 3: update() with note in payload preserves note ─────────────────────

@pytest.mark.django_db
def test_edit_save_with_note_in_detaylar_preserves_note(coach, student):
    """update() deletes then rebuilds detaylar; if the payload includes the note row it must survive."""
    monday = date.today()
    grup = _make_konu_task_with_videos_and_note(student, monday)

    tasks_svc.update(
        coach, grup.id,
        tarih=monday,
        ders_title=grup.ders_title,
        ozel_sure_dk=grup.ozel_sure_dk,
        aktivite_tipi=grup.aktivite_tipi,
        detaylar=[
            {"aciklama": "Video 1", "sure_bilgisi": "30 dk"},
            {"aciklama": "Video 2", "sure_bilgisi": "20 dk"},
            {"aciklama": "bu konuya dikkat et", "sure_bilgisi": ""},
        ],
        meta=grup.meta,
    )

    detaylar = list(grup.detaylar.values("aciklama", "sure_bilgisi"))
    note_rows = [d for d in detaylar if not d["sure_bilgisi"]]
    assert len(note_rows) == 1
    assert note_rows[0]["aciklama"] == "bu konuya dikkat et"
    video_rows = [d for d in detaylar if d["sure_bilgisi"]]
    assert len(video_rows) == 2


# ── Test 4: expired student → 403 on copy endpoint ───────────────────────────

@pytest.mark.django_db
def test_copy_expired_student_returns_403(coach, student):
    from users_app.models import CoachStudent

    monday = date.today()
    tuesday = monday + timedelta(days=1)

    CoachStudent.objects.create(
        coach=coach, student=student, active=True,
        source=CoachStudent.SOURCE_VAGUS,
        next_payment_due=date.today() - timedelta(days=1),
    )

    grup = GorevGrubu.objects.create(
        student=student, tarih=monday,
        aktivite_tipi="tekrar", ders_title="Test", sira_no=1,
    )

    c = Client()
    c.force_login(coach)
    resp = c.post(
        f'/coach/tasks/api/gorev/{grup.id}/copy',
        data=json.dumps({"hedef_tarih": tuesday.isoformat()}),
        content_type='application/json',
    )
    assert resp.status_code == 403
    # No copy created — only the original task exists
    assert GorevGrubu.objects.filter(student=student).count() == 1

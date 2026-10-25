"""
Tests for note + video preservation when moving/copying coach tasks.

Contract verified:
- move_to_date changes ONLY tarih and sira_no (meta, detaylar, note, duration untouched)
- copy_to_date preserves everything including the note
- moving a task without videos has no regression
- expired student → 403 on move endpoint
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


# ── Test 1: move preserves note, videos, meta, duration ───────────────────────

@pytest.mark.django_db
def test_move_konu_anlatimi_with_videos_preserves_all_fields(coach, student):
    monday = date.today()
    tuesday = monday + timedelta(days=1)

    grup = _make_konu_task_with_videos_and_note(student, monday)
    original_meta = dict(grup.meta)
    original_sure = grup.ozel_sure_dk
    original_detaylar = list(grup.detaylar.values("aciklama", "sure_bilgisi"))

    ok = tasks_svc.move_to_date(coach, grup.id, tuesday)

    assert ok is True
    grup.refresh_from_db()

    # Only tarih and sira_no changed
    assert grup.tarih == tuesday
    assert grup.ders_title == "Matematik - Konu Anlatimi"
    assert grup.ozel_sure_dk == original_sure
    assert grup.meta == original_meta

    # detaylar (videos + note) unchanged
    detaylar_after = list(grup.detaylar.values("aciklama", "sure_bilgisi"))
    assert len(detaylar_after) == 3
    note_rows = [d for d in detaylar_after if not d["sure_bilgisi"]]
    assert len(note_rows) == 1
    assert note_rows[0]["aciklama"] == "bu konuya dikkat et"
    video_rows = [d for d in detaylar_after if d["sure_bilgisi"]]
    assert len(video_rows) == 2

    # Original day has no tasks left
    assert GorevGrubu.objects.filter(student=student, tarih=monday).count() == 0


# ── Test 2: copy preserves note, videos, meta, duration ───────────────────────

@pytest.mark.django_db
def test_copy_konu_anlatimi_with_videos_preserves_all_fields(coach, student):
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

    # Original also still has 3 detaylar
    assert grup.detaylar.count() == 3


# ── Test 3: move task without videos — no regression ─────────────────────────

@pytest.mark.django_db
def test_move_task_without_videos_no_regression(coach, student):
    monday = date.today()
    wednesday = monday + timedelta(days=2)

    grup = GorevGrubu.objects.create(
        student=student, tarih=monday,
        aktivite_tipi="soru_cozumu",
        ders_title="TYT - Matematik",
        ozel_sure_dk=45, sira_no=1, meta=None,
    )
    GrupDetay.objects.create(grup=grup, aciklama="30 soru çöz", sure_bilgisi="")

    ok = tasks_svc.move_to_date(coach, grup.id, wednesday)

    assert ok is True
    grup.refresh_from_db()
    assert grup.tarih == wednesday
    assert grup.ozel_sure_dk == 45
    detaylar = list(grup.detaylar.values_list("aciklama", flat=True))
    assert detaylar == ["30 soru çöz"]
    assert GorevGrubu.objects.filter(student=student, tarih=monday).count() == 0


# ── Test 4: expired student → 403 on move endpoint ───────────────────────────

@pytest.mark.django_db
def test_move_expired_student_returns_403(coach, student):
    from datetime import timedelta
    from django.utils import timezone
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
        f'/coach/tasks/api/gorev/{grup.id}/move',
        data=json.dumps({"hedef_tarih": tuesday.isoformat()}),
        content_type='application/json',
    )
    assert resp.status_code == 403
    # Task must stay on original date
    grup.refresh_from_db()
    assert grup.tarih == monday

"""
Tests for LEGACY_PLAYLISTS_ENABLED feature flag.
"""
from unittest.mock import patch

import pytest
from django.test import override_settings
from model_bakery import baker


# ── Test 1: flag off — views return empty, no outgoing HTTP call ───────────────

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_flag_off_returns_empty_no_http_call(client):
    coach = baker.make('users_app.User', role='coach', is_approved=True)
    client.force_login(coach)

    with patch('tasks_app.services.api_client._get') as mock_get:
        r_ders = client.get('/coach/tasks/api/dersler')
        r_list = client.get('/coach/tasks/api/oynatma-listeleri/1')
        r_vid  = client.get('/coach/tasks/api/videolar/1')

    assert r_ders.status_code == 200
    assert r_ders.json() == {'dersler': []}
    assert r_list.status_code == 200
    assert r_list.json() == {'listeler': []}
    assert r_vid.status_code == 200
    assert r_vid.json() == {'videolar': []}
    mock_get.assert_not_called()


# ── Test 2: flag on — views call the api_client normally ──────────────────────

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=True)
def test_flag_on_calls_api_client(client):
    coach = baker.make('users_app.User', role='coach', is_approved=True)
    client.force_login(coach)

    sentinel = [{'Id': 9, 'Title': 'Test Ders'}]
    with patch('tasks_app.services.api_client._get', return_value={'dersler': sentinel}):
        r = client.get('/coach/tasks/api/dersler')

    assert r.status_code == 200
    assert r.json()['dersler'] == [{'id': 9, 'ad': 'Test Ders'}]


# ── Test 3: editing a legacy task with flag off — meta.videos survives ─────────

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_legacy_task_meta_videos_intact_when_flag_off(client):
    """
    GorevDetailView.get() returns meta.videos intact; the edit endpoint (PUT)
    accepts a re-save with those same videos and preserves them.

    What could NOT be verified in a browser: the JS _hydrateKonuEdit path that
    restores videolar from meta.videos (so the video checkboxes populate).
    Students see detaylar[].aciklama / sure_bilgisi (stored in GrupDetay rows),
    not meta.videos directly — student display is unaffected by the flag.

    Note: legacy meta.videos stores {id, title, duration} with id being a SQLite
    integer, NOT a YouTube URL.  No video link is stored; students cannot click
    to watch legacy videos.  This is a pre-existing limitation of the legacy
    catalog, not introduced by this flag.
    """
    coach   = baker.make('users_app.User', role='coach', is_approved=True)
    student = baker.make('users_app.User', role='student', coach=coach)
    baker.make('users_app.CoachStudent', coach=coach, student=student, active=True)

    saved_videos = [{'id': 42, 'title': 'Test Video', 'duration': 15}]
    grup = baker.make(
        'tasks_app.GorevGrubu',
        student=student,
        aktivite_tipi='konu_anlatimi',
        ders_title='Matematik - Konu Anlatımı',
        meta={
            'sinav_tipi': 'TYT',
            'ders_id': 3,
            'liste_id': 7,
            'liste_baslik': 'Test Liste',
            'videos': saved_videos,
        },
    )
    baker.make('tasks_app.GrupDetay', grup=grup, aciklama='Test Video', sure_bilgisi='15 dk')

    client.force_login(coach)

    r = client.get(f'/coach/tasks/api/gorev/{grup.pk}')
    assert r.status_code == 200
    data = r.json()
    assert data['meta']['videos'] == saved_videos, 'meta.videos must be returned intact'
    assert data['meta']['liste_baslik'] == 'Test Liste'

    import json
    put_payload = {
        'tarih': str(grup.tarih),
        'aktivite_tipi': 'konu_anlatimi',
        'ders_title': grup.ders_title,
        'sinav_tipi': 'TYT',
        'konu_ders_id': 3,
        'liste_id': 7,
        'liste_baslik': 'Test Liste',
        'videos': saved_videos,
        'detaylar': json.dumps([{'aciklama': 'Test Video', 'sure_bilgisi': '15 dk'}]),
    }
    r2 = client.put(
        f'/coach/tasks/api/gorev/{grup.pk}',
        data=json.dumps(put_payload),
        content_type='application/json',
    )
    assert r2.status_code == 200
    assert r2.json()['ok'] is True

    grup.refresh_from_db()
    assert grup.meta['videos'] == saved_videos, 'meta.videos must survive a re-save'

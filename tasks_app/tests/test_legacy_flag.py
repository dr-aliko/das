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


# ── Test 4: flag off — DerslerView builds list from own playlists ─────────────

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_dersler_own_playlists_flag_off(client):
    """DerslerView returns subjects from the coach's own playlists + unspecified entry."""
    from exams_app.models import Subject
    coach = baker.make('users_app.User', role='coach', is_approved=True)
    # name includes exam_type prefix so display_name strips it → 'Matematik', 'Fizik'
    math = baker.make(Subject, name='TYT Matematik', exam_type='TYT', excluded_from_planning=False)
    phys = baker.make(Subject, name='AYT Fizik', exam_type='AYT', excluded_from_planning=False)
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=math, exam_type='TYT')
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=phys, exam_type='AYT')
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=None, exam_type='TYT')

    client.force_login(coach)
    r = client.get('/coach/tasks/api/dersler')
    assert r.status_code == 200
    dersler = r.json()['dersler']

    ids = {d['id'] for d in dersler}
    names = {d['ad'] for d in dersler}
    assert f'sub_{math.pk}' in ids
    assert f'sub_{phys.pk}' in ids
    assert 'sub_0' in ids
    assert 'Matematik' in names
    assert 'Fizik' in names
    assert 'Ders belirtilmemiş' in names


# ── Test 5: flag off — ders.ad matches playlist subject_display (filter chain) ──

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_dersler_ad_matches_playlist_subject_display(client):
    """ders.ad must equal playlist.subject_display so the JS filter chain works."""
    from exams_app.models import Subject
    coach = baker.make('users_app.User', role='coach', is_approved=True)
    math = baker.make(Subject, name='TYT Matematik', exam_type='TYT', excluded_from_planning=False)
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=math, exam_type='TYT')
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=None, exam_type='TYT')

    client.force_login(coach)

    dersler = client.get('/coach/tasks/api/dersler').json()['dersler']
    playlists = client.get('/coach/tasks/api/youtube/list').json()['playlists']

    ders_math = next(d for d in dersler if d['id'] == f'sub_{math.pk}')
    pl_math = next(p for p in playlists if p['subject_display'] == 'Matematik')
    assert ders_math['ad'] == pl_math['subject_display']

    ders_unspc = next(d for d in dersler if d['id'] == 'sub_0')
    pl_unspc = next(p for p in playlists if p['subject_display'] == '')
    assert ders_unspc['id'] == 'sub_0'
    assert pl_unspc['subject_display'] == ''


# ── Test 6: same display_name for TYT and AYT → no duplicates, disambiguated ──

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_dersler_no_duplicates_for_same_display_name(client):
    """Two subjects with the same display_name (e.g. TYT vs AYT Matematik) must
    appear as 'Matematik (AYT)' and 'Matematik (TYT)', never as two plain 'Matematik' entries."""
    from exams_app.models import Subject
    coach = baker.make('users_app.User', role='coach', is_approved=True)
    tyt_mat = baker.make(Subject, name='TYT Matematik', exam_type='TYT', excluded_from_planning=False)
    ayt_mat = baker.make(Subject, name='AYT Matematik', exam_type='AYT', excluded_from_planning=False)
    # Unique subject, no name collision
    tyt_bio = baker.make(Subject, name='TYT Biyoloji', exam_type='TYT', excluded_from_planning=False)
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=tyt_mat, exam_type='TYT')
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=ayt_mat, exam_type='AYT')
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=tyt_bio, exam_type='TYT')

    client.force_login(coach)
    r = client.get('/coach/tasks/api/dersler')
    assert r.status_code == 200
    dersler = r.json()['dersler']

    names = [d['ad'] for d in dersler]
    # No plain 'Matematik' — must be disambiguated
    assert 'Matematik' not in names
    assert 'Matematik (TYT)' in names
    assert 'Matematik (AYT)' in names
    # Unique subject keeps its short name
    assert 'Biyoloji' in names
    # Alphabetical order: Biyoloji < Matematik (AYT) < Matematik (TYT)
    assert names.index('Biyoloji') < names.index('Matematik (AYT)')
    assert names.index('Matematik (AYT)') < names.index('Matematik (TYT)')
    # No duplicates
    assert len(names) == len(set(names))


# ── Test 7: empty coach → empty dersler list, no error ────────────────────────

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_dersler_empty_for_coach_with_no_playlists(client):
    """Coach with no imported playlists gets an empty dersler list, not an error."""
    coach = baker.make('users_app.User', role='coach', is_approved=True)
    client.force_login(coach)
    r = client.get('/coach/tasks/api/dersler')
    assert r.status_code == 200
    assert r.json() == {'dersler': []}


# ── Test 8: exam_type field present; tip filter by exam_type works; sub_0 last ─

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_dersler_exam_type_field_and_tip_filter(client):
    """Each entry carries exam_type; tip-based client filter works; sub_0 is last."""
    from exams_app.models import Subject
    coach = baker.make('users_app.User', role='coach', is_approved=True)
    tyt_mat = baker.make(Subject, name='TYT Matematik', exam_type='TYT', excluded_from_planning=False)
    ayt_mat = baker.make(Subject, name='AYT Matematik', exam_type='AYT', excluded_from_planning=False)
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=tyt_mat, exam_type='TYT')
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=ayt_mat, exam_type='AYT')
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=None, exam_type='TYT')

    client.force_login(coach)
    dersler = client.get('/coach/tasks/api/dersler').json()['dersler']

    by_id = {d['id']: d for d in dersler}
    tyt_entry = by_id[f'sub_{tyt_mat.pk}']
    ayt_entry = by_id[f'sub_{ayt_mat.pk}']

    # Each entry has the correct exam_type field
    assert tyt_entry['exam_type'] == 'TYT'
    assert ayt_entry['exam_type'] == 'AYT'

    # display_name matches subject_display (used by filteredYtListeler)
    assert tyt_entry['display_name'] == 'Matematik'
    assert ayt_entry['display_name'] == 'Matematik'

    # ad carries the disambiguating suffix shown in the selector
    assert tyt_entry['ad'] == 'Matematik (TYT)'
    assert ayt_entry['ad'] == 'Matematik (AYT)'

    # sub_0 has empty exam_type and is last
    assert dersler[-1]['id'] == 'sub_0'
    assert dersler[-1]['exam_type'] == ''
    assert dersler[-1]['display_name'] == ''

    # flag=off → filteredDersler returns all entries unfiltered
    assert len(dersler) == 3  # TYT Matematik, AYT Matematik, sub_0
    assert any(d['ad'] == 'Matematik (TYT)' for d in dersler)
    assert any(d['ad'] == 'Matematik (AYT)' for d in dersler)


# ── Test 9: single exam_type coach — entry returned unfiltered ────────────────

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_dersler_single_exam_type_coach(client):
    """Coach with only TYT playlists: the TYT entry appears for all sinav types (no filtering)."""
    from exams_app.models import Subject
    coach = baker.make('users_app.User', role='coach', is_approved=True)
    math = baker.make(Subject, name='TYT Matematik', exam_type='TYT', excluded_from_planning=False)
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=math, exam_type='TYT')

    client.force_login(coach)
    dersler = client.get('/coach/tasks/api/dersler').json()['dersler']

    assert len(dersler) == 1
    assert dersler[0]['ad'] == 'Matematik'
    assert dersler[0]['exam_type'] == 'TYT'
    assert dersler[0]['display_name'] == 'Matematik'

    # flag=off → filteredDersler returns all entries; both TYT and AYT students see this entry
    assert len(dersler) == 1


# ── Test 10: production fixture — all entries returned, no silent drops ────────

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_dersler_production_fixture_no_entries_dropped(client):
    """Mirrors real production data: coach has TYT-only subjects (Geometri, Matematik)
    plus mixed AYT subjects. All entries must appear regardless of sinav_tipi."""
    from exams_app.models import Subject
    coach = baker.make('users_app.User', role='coach', is_approved=True)

    # TYT-only subjects (the ones that disappeared in production when sinav_tipi=AYT)
    geo = baker.make(Subject, name='TYT Geometri', exam_type='TYT', excluded_from_planning=False)
    mat = baker.make(Subject, name='TYT Matematik', exam_type='TYT', excluded_from_planning=False)
    fiz = baker.make(Subject, name='TYT Fizik', exam_type='TYT', excluded_from_planning=False)

    # AYT subjects
    ayt_mat = baker.make(Subject, name='AYT Matematik', exam_type='AYT', excluded_from_planning=False)
    ayt_bio = baker.make(Subject, name='AYT Biyoloji', exam_type='AYT', excluded_from_planning=False)

    for subj, etype in [(geo, 'TYT'), (mat, 'TYT'), (fiz, 'TYT'), (ayt_mat, 'AYT'), (ayt_bio, 'AYT')]:
        baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=subj, exam_type=etype)

    client.force_login(coach)
    dersler = client.get('/coach/tasks/api/dersler').json()['dersler']

    ids = {d['id'] for d in dersler}
    assert f'sub_{geo.pk}' in ids, 'Geometri (TYT) must not be dropped'
    assert f'sub_{mat.pk}' in ids, 'Matematik (TYT) must not be dropped'
    assert f'sub_{fiz.pk}' in ids, 'Fizik (TYT) must not be dropped'
    assert f'sub_{ayt_mat.pk}' in ids
    assert f'sub_{ayt_bio.pk}' in ids
    assert len(dersler) == 5


# ── Test 11: TYT ders exam_type survives — filteredYtListeler chain correct ───

@pytest.mark.django_db
@override_settings(LEGACY_PLAYLISTS_ENABLED=False)
def test_tyt_ders_exam_type_enables_playlist_filter_for_ayt_student(client):
    """Geometri (exam_type=TYT) ders entry carries exam_type='TYT'.
    filteredYtListeler flag=OFF filters by ders.exam_type, not sinav_tipi,
    so TYT Geometri playlists are shown even when a student's sinav_tipi is AYT."""
    from exams_app.models import Subject
    coach = baker.make('users_app.User', role='coach', is_approved=True)
    geo = baker.make(Subject, name='TYT Geometri', exam_type='TYT', excluded_from_planning=False)
    baker.make('tasks_app.YouTubePlaylist', imported_by=coach, subject=geo, exam_type='TYT',
               title='Geometri Playlist 1')

    client.force_login(coach)
    dersler = client.get('/coach/tasks/api/dersler').json()['dersler']

    geo_entry = next(d for d in dersler if d['id'] == f'sub_{geo.pk}')
    assert geo_entry['exam_type'] == 'TYT'
    assert geo_entry['display_name'] == 'Geometri'

    # The playlist carries exam_type='TYT' and subject_display='Geometri'.
    # When flag=OFF, filteredYtListeler uses ders.exam_type (TYT) — not sinav_tipi (AYT) —
    # so the playlist passes the exam_type gate and then matches by subject_display.
    playlists = client.get('/coach/tasks/api/youtube/list').json()['playlists']
    # subject_display is computed from subject.display_name in the view
    geo_pl = [p for p in playlists if p['subject_display'] == 'Geometri']
    assert len(geo_pl) == 1
    assert geo_pl[0]['exam_type'] == 'TYT'
    # ders.display_name == playlist.subject_display → filteredYtListeler match is guaranteed
    assert geo_entry['display_name'] == geo_pl[0]['subject_display']

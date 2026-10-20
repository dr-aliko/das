"""
YouTube import service tests — mocked YouTube API client.
"""
import json
import socket
from unittest.mock import MagicMock, patch

import pytest
from model_bakery import baker

from tasks_app.models import GorevGrubu, YouTubePlaylist, YouTubeVideo
from tasks_app.services.youtube_playlist_importer import (
    PlaylistNotFound, YouTubeAPIError, sync_playlist,
)


def _make_yt_mock(title='Test PL', channel='CH', item_count=2, pages=None, durations=None):
    """Return a MagicMock YouTube client configured for a single-coach scenario."""
    mock_yt = MagicMock()

    # playlists().list().execute()
    mock_yt.playlists.return_value.list.return_value.execute.return_value = {
        'items': [{'snippet': {'title': title, 'channelTitle': channel},
                   'contentDetails': {'itemCount': item_count}}],
    }

    # playlistItems().list().execute() - accepts side_effect list of pages
    if pages is not None:
        mock_yt.playlistItems.return_value.list.return_value.execute.side_effect = pages
    else:
        mock_yt.playlistItems.return_value.list.return_value.execute.return_value = {
            'items': [], 'nextPageToken': None,
        }

    # videos().list().execute() - returns durations for the requested ids
    durations = durations or {}

    def _vid_list(**kwargs):
        ids = kwargs.get('id', '').split(',')
        items = [{'id': i, 'contentDetails': {'duration': durations.get(i, 'PT5M')}} for i in ids if i]
        m = MagicMock()
        m.execute.return_value = {'items': items}
        return m

    mock_yt.videos.return_value.list.side_effect = _vid_list
    return mock_yt


# ── Test 1: sync keeps referenced videos ──────────────────────────────────────

@pytest.mark.django_db
def test_sync_keeps_referenced_videos():
    """Videos referenced in GorevGrubu.meta are kept even when removed from playlist."""
    coach   = baker.make('users_app.User', role='coach')
    student = baker.make('users_app.User', role='student')
    pl = baker.make('tasks_app.YouTubePlaylist', playlist_id='PLtest', imported_by=coach,
                    exam_type='TYT')
    v1 = baker.make('tasks_app.YouTubeVideo', playlist=pl, video_id='vid1', position=0)
    v2 = baker.make('tasks_app.YouTubeVideo', playlist=pl, video_id='vid2', position=1)

    # GorevGrubu references v2 by PK
    baker.make('tasks_app.GorevGrubu', student=student, aktivite_tipi='konu_anlatimi',
               meta={'source': 'youtube', 'youtube_playlist_pk': pl.pk,
                     'videos': [{'id': v2.pk, 'title': v2.title, 'duration': 5}]})

    # YouTube now returns only vid1 (vid2 was removed from playlist)
    pages = [{'items': [{'snippet': {'title': 'Video 1 Updated', 'position': 0},
                          'contentDetails': {'videoId': 'vid1'}}]}]
    mock_yt = _make_yt_mock(pages=pages)

    with patch('tasks_app.services.youtube_playlist_importer._build_youtube', return_value=mock_yt):
        result = sync_playlist('PLtest', None, 'TYT', coach)

    # v2 must still exist — it is referenced
    assert YouTubeVideo.objects.filter(pk=v2.pk).exists(), 'Referenced video must be kept'
    # v1 must still exist — it is in the new playlist
    assert YouTubeVideo.objects.filter(pk=v1.pk).exists()
    # v1 title should be updated
    v1.refresh_from_db()
    assert v1.title == 'Video 1 Updated'
    # Summary: 0 removed (v2 kept because referenced)
    assert '0 kaldırıldı' in result['summary']
    assert '1 güncellendi' in result['summary']


# ── Test 2: HttpError / timeout returns Turkish message, no key= in message ───

@pytest.mark.django_db
def test_api_error_no_key_in_message():
    """HttpError and timeout: YouTubeAPIError message is Turkish, never contains 'key='."""
    coach = baker.make('users_app.User', role='coach')

    # Simulate HttpError with key in URL (403 quota exceeded)
    from googleapiclient.errors import HttpError

    fake_resp = MagicMock()
    fake_resp.status = 403
    quota_body = json.dumps({'error': {'errors': [{'reason': 'quotaExceeded'}]}}).encode()
    http_exc = HttpError(resp=fake_resp, content=quota_body,
                         uri='https://youtube.googleapis.com/youtube/v3/playlists?key=AIzaFAKE123KEY')

    mock_yt = MagicMock()
    mock_yt.playlists.return_value.list.return_value.execute.side_effect = http_exc

    with patch('tasks_app.services.youtube_playlist_importer._build_youtube', return_value=mock_yt):
        with pytest.raises(YouTubeAPIError) as exc_info:
            sync_playlist('PLquota', None, 'TYT', coach)

    msg = str(exc_info.value)
    assert 'key=' not in msg, 'API key must not appear in user-facing error'
    assert 'kota' in msg.lower() or 'quota' in msg.lower() or 'günlük' in msg.lower()

    # Test timeout too
    mock_yt2 = MagicMock()
    mock_yt2.playlists.return_value.list.return_value.execute.side_effect = socket.timeout('timed out')

    with patch('tasks_app.services.youtube_playlist_importer._build_youtube', return_value=mock_yt2):
        with pytest.raises(YouTubeAPIError) as exc_info2:
            sync_playlist('PLtimeout', None, 'TYT', coach)

    msg2 = str(exc_info2.value)
    assert 'key=' not in msg2
    assert 'yanıt vermiyor' in msg2.lower() or 'deneyin' in msg2.lower()


# ── Test 3: retry (calling sync_playlist twice) creates no duplicates ─────────

@pytest.mark.django_db
def test_no_duplicates_on_retry():
    """Calling sync_playlist twice on the same playlist leaves exactly N videos, no duplicates."""
    coach = baker.make('users_app.User', role='coach')

    pages = [{'items': [
        {'snippet': {'title': f'Vid {i}', 'position': i}, 'contentDetails': {'videoId': f'v{i}'}}
        for i in range(3)
    ]}]
    durations = {f'v{i}': 'PT4M' for i in range(3)}

    for _ in range(2):
        mock_yt = _make_yt_mock(pages=list(pages), durations=durations)
        with patch('tasks_app.services.youtube_playlist_importer._build_youtube', return_value=mock_yt):
            result = sync_playlist('PLretry', None, 'TYT', coach)

    pl = YouTubePlaylist.objects.get(pk=result['playlist_pk'])
    assert pl.videos.count() == 3, 'Exactly 3 videos after two syncs, no duplicates'

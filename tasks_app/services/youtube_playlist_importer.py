"""
YouTube Playlist Importer — Django port of playlist_bot.py.

Public API:
  extract_playlist_id(url)             -> str | None
  detect_subject_and_exam_type(title)  -> (Subject | None, str | None)
  fetch_playlist_meta(playlist_id)     -> dict  (title, channel_title, video_count)
  import_playlist(pid, subject, exam_type, imported_by) -> YouTubePlaylist
"""
from __future__ import annotations

import re

import isodate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from django.conf import settings
from django.db import transaction


# ── Exceptions ─────────────────────────────────────────────────────────────────

class InvalidPlaylistURL(Exception):
    pass


class PlaylistNotFound(Exception):
    pass


class YouTubeAPIError(Exception):
    pass


# ── URL extraction (matches playlist_bot.py regex) ─────────────────────────────

_PLAYLIST_RE = re.compile(
    r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?(?:[^#]*&)?list=([a-zA-Z0-9_-]+)'
)


def extract_playlist_id(url: str) -> str | None:
    """Return the playlist ID embedded in a YouTube playlist URL, or None."""
    m = _PLAYLIST_RE.search(url or '')
    pid = m.group(1) if m else None
    return pid if pid and len(pid) >= 10 else None


# ── Subject / exam-type detection ─────────────────────────────────────────────

_SUBJECT_KEYWORDS: dict[str, list[str]] = {
    'Matematik':     ['matematik', 'problem', 'problemler'],
    'Geometri':      ['geometri'],
    'Fizik':         ['fizik'],
    'Kimya':         ['kimya'],
    'Biyoloji':      ['biyoloji'],
    'Türkçe':        ['türkçe', 'edebiyat', 'turkce'],
    'Tarih':         ['tarih'],
    'Coğrafya':      ['coğrafya', 'cografya'],
    'Felsefe':       ['felsefe'],
    'Din Kültürü':   ['din kültürü', 'din kulturu'],
}


def detect_subject_and_exam_type(title: str):
    """
    Returns (Subject | None, exam_type_str | None).
    Looks for TYT/AYT anywhere in the title; matches subjects by keyword.
    """
    from exams_app.models import Subject

    t = title.lower()

    exam_type = 'TYT' if 'tyt' in t else ('AYT' if 'ayt' in t else None)

    subject_name = None
    for name, keywords in _SUBJECT_KEYWORDS.items():
        if any(k in t for k in keywords):
            subject_name = name
            break

    if not subject_name:
        return None, exam_type

    qs = Subject.objects.filter(name__icontains=subject_name)
    if exam_type:
        qs = qs.filter(exam_type=exam_type)
    subject = qs.first()

    if subject and not exam_type:
        exam_type = subject.exam_type

    return subject, exam_type


# ── YouTube API helpers ────────────────────────────────────────────────────────

def _build_youtube():
    key = getattr(settings, 'YOUTUBE_API_KEY', '')
    if not key:
        msg = 'YouTube API anahtarı yapılandırılmamış.'
        if getattr(settings, 'DEBUG', False):
            msg += (
                ' Cozum: .env dosyasina YOUTUBE_API_KEY=AIza... satirini ekleyin.'
                ' Anahtari Google Cloud Console -> YouTube Data API v3 -> Kimlik Bilgileri'
                ' bolumunden olusturabilirsiniz.'
            )
        raise YouTubeAPIError(msg)
    return build('youtube', 'v3', developerKey=key)


def _parse_duration(duration_str: str) -> int:
    """ISO 8601 duration → whole minutes."""
    try:
        return int(isodate.parse_duration(duration_str).total_seconds() / 60)
    except Exception:
        return 0


def fetch_playlist_meta(playlist_id: str) -> dict:
    """
    Returns {title, channel_title, video_count} for the given playlist ID.
    Raises PlaylistNotFound or YouTubeAPIError on failure.
    """
    try:
        yt = _build_youtube()
        resp = yt.playlists().list(
            part='snippet,contentDetails',
            id=playlist_id,
        ).execute()
    except HttpError as exc:
        raise YouTubeAPIError(str(exc)) from exc

    items = resp.get('items', [])
    if not items:
        raise PlaylistNotFound(f'Playlist bulunamadi ya da gizli: {playlist_id}')

    snippet = items[0]['snippet']
    count = items[0].get('contentDetails', {}).get('itemCount', 0)
    return {
        'title':         snippet['title'],
        'channel_title': snippet.get('channelTitle', ''),
        'video_count':   count,
    }


@transaction.atomic
def import_playlist(playlist_id: str, subject, exam_type: str, imported_by) -> 'YouTubePlaylist':
    """
    Upserts YouTubePlaylist, replaces its video list, and returns the instance.
    Raises PlaylistNotFound or YouTubeAPIError on API failure.
    """
    from tasks_app.models import YouTubePlaylist, YouTubeVideo

    try:
        yt = _build_youtube()
        meta = fetch_playlist_meta(playlist_id)

        playlist_obj, _ = YouTubePlaylist.objects.update_or_create(
            playlist_id=playlist_id,
            defaults={
                'title':         meta['title'],
                'channel_title': meta['channel_title'],
                'subject':       subject,
                'exam_type':     exam_type,
                'imported_by':   imported_by,
            },
        )

        # Replace video list (mirrors bot's delete-then-insert pattern)
        playlist_obj.videos.all().delete()

        videos_to_create: list[YouTubeVideo] = []
        next_page_token = None

        while True:
            items_resp = yt.playlistItems().list(
                part='snippet,contentDetails',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token,
            ).execute()

            valid_items = [
                item for item in items_resp.get('items', [])
                if item['snippet']['title'] not in ('Private video', 'Deleted video')
            ]

            if valid_items:
                video_ids = [item['contentDetails']['videoId'] for item in valid_items]
                vid_resp = yt.videos().list(
                    part='contentDetails',
                    id=','.join(video_ids),
                ).execute()
                durations = {
                    v['id']: _parse_duration(v['contentDetails']['duration'])
                    for v in vid_resp.get('items', [])
                }

                for item in valid_items:
                    vid_id = item['contentDetails']['videoId']
                    videos_to_create.append(YouTubeVideo(
                        playlist=playlist_obj,
                        video_id=vid_id,
                        title=item['snippet']['title'],
                        duration_min=durations.get(vid_id, 0),
                        position=item['snippet']['position'],
                    ))

            next_page_token = items_resp.get('nextPageToken')
            if not next_page_token:
                break

        YouTubeVideo.objects.bulk_create(videos_to_create, ignore_conflicts=True)
        return playlist_obj

    except (PlaylistNotFound, YouTubeAPIError):
        raise
    except HttpError as exc:
        raise YouTubeAPIError(str(exc)) from exc
    except Exception as exc:
        raise YouTubeAPIError(str(exc)) from exc

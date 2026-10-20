"""
YouTube Playlist Importer.

Public API:
  extract_playlist_id(url)             -> str | None
  detect_subject_and_exam_type(title)  -> (Subject | None, str | None)
  fetch_playlist_meta(playlist_id)     -> dict  (title, channel_title, video_count)
  sync_playlist(pid, subject, exam_type, imported_by, progress_cb=None) -> dict
"""
from __future__ import annotations

import json
import logging
import re
import socket
import time

import httplib2
import isodate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from django.conf import settings
from django.db import transaction

logger = logging.getLogger('tasks_app.youtube')

_KEY_RE = re.compile(r'key=[^&\s"]+')

_MAX_PAGES = 200


# ── Exceptions ─────────────────────────────────────────────────────────────────

class InvalidPlaylistURL(Exception):
    pass


class PlaylistNotFound(Exception):
    pass


class YouTubeAPIError(Exception):
    pass


# ── URL extraction ─────────────────────────────────────────────────────────────

_PLAYLIST_RE = re.compile(
    r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?(?:[^#]*&)?list=([a-zA-Z0-9_-]+)'
)


def extract_playlist_id(url: str) -> str | None:
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


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_youtube():
    key = settings.YOUTUBE_API_KEY
    if not key:
        msg = 'YouTube API anahtarı yapılandırılmamış.'
        if settings.DEBUG:
            msg += (
                ' Çözüm: .env dosyasına YOUTUBE_API_KEY=AIza... satırını ekleyin.'
            )
        raise YouTubeAPIError(msg)
    http = httplib2.Http(timeout=15)
    return build('youtube', 'v3', developerKey=key, http=http, num_retries=2)


def _parse_duration(duration_str: str) -> int:
    try:
        return int(isodate.parse_duration(duration_str).total_seconds() / 60)
    except Exception:
        return 0


def _redact(text: str) -> str:
    return _KEY_RE.sub('key=REDACTED', text)


def _log_http_error(exc: HttpError, context: str = '') -> None:
    sanitized = _redact(str(exc))
    logger.error('YouTube API error%s: %s', f' [{context}]' if context else '', sanitized)


def _http_error_to_user_msg(exc: HttpError) -> str:
    code = int(exc.resp.status)
    if code == 404:
        return 'Liste bulunamadı veya gizli.'
    if code == 403:
        try:
            details = json.loads(exc.content.decode('utf-8', errors='replace'))
            reasons = [e.get('reason', '') for e in details.get('error', {}).get('errors', [])]
            if any('quota' in r.lower() for r in reasons):
                return 'Günlük YouTube kotası doldu.'
        except Exception:
            pass
        return 'YouTube API erişim hatası.'
    if code in (408, 429, 503):
        return 'YouTube yanıt vermiyor, lütfen tekrar deneyin.'
    return 'Beklenmeyen bir YouTube hatası oluştu.'


def _find_referenced_video_pks(playlist_pk: int) -> set:
    """Return set of YouTubeVideo PKs that appear in any GorevGrubu.meta.videos."""
    from tasks_app.models import GorevGrubu
    referenced: set = set()
    qs = GorevGrubu.objects.filter(
        aktivite_tipi='konu_anlatimi',
        meta__source='youtube',
        meta__youtube_playlist_pk=playlist_pk,
    ).values_list('meta', flat=True)
    for meta in qs:
        if not meta:
            continue
        for v in meta.get('videos', []):
            vid_pk = v.get('id')
            if vid_pk is not None:
                referenced.add(vid_pk)
    return referenced


# ── Fetch all pages (network only, no transaction) ────────────────────────────

def _fetch_all_pages(yt, playlist_id: str, progress_cb=None) -> list:
    """
    Fetch all playlist items and video durations outside any transaction.
    Returns list of {video_id, title, duration_min, position}.
    """
    videos: list = []
    next_page_token = None
    page = 0
    seen_tokens: set = set()
    start = time.monotonic()

    while True:
        if page >= _MAX_PAGES:
            logger.warning('YouTube page cap (%d) reached for %s', _MAX_PAGES, playlist_id)
            break

        if next_page_token:
            if next_page_token in seen_tokens:
                logger.warning('Repeated page token for %s, stopping', playlist_id)
                break
            seen_tokens.add(next_page_token)

        try:
            items_resp = yt.playlistItems().list(
                part='snippet,contentDetails',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token,
            ).execute(num_retries=2)
        except HttpError as exc:
            _log_http_error(exc, playlist_id)
            raise YouTubeAPIError(_http_error_to_user_msg(exc)) from exc
        except (socket.timeout, TimeoutError, httplib2.ServerNotFoundError) as exc:
            logger.error('YouTube timeout for %s: %s', playlist_id, exc)
            raise YouTubeAPIError('YouTube yanıt vermiyor, lütfen tekrar deneyin.') from exc

        page += 1

        valid_items = [
            item for item in items_resp.get('items', [])
            if item['snippet']['title'] not in ('Private video', 'Deleted video')
        ]

        if valid_items:
            vid_ids = [item['contentDetails']['videoId'] for item in valid_items]
            try:
                vid_resp = yt.videos().list(
                    part='contentDetails',
                    id=','.join(vid_ids),
                ).execute(num_retries=2)
            except HttpError as exc:
                _log_http_error(exc, playlist_id)
                raise YouTubeAPIError(_http_error_to_user_msg(exc)) from exc
            except (socket.timeout, TimeoutError, httplib2.ServerNotFoundError) as exc:
                logger.error('YouTube timeout (durations) for %s: %s', playlist_id, exc)
                raise YouTubeAPIError('YouTube yanıt vermiyor, lütfen tekrar deneyin.') from exc

            durations = {
                v['id']: _parse_duration(v['contentDetails']['duration'])
                for v in vid_resp.get('items', [])
            }

            for item in valid_items:
                vid_id = item['contentDetails']['videoId']
                videos.append({
                    'video_id':     vid_id,
                    'title':        item['snippet']['title'],
                    'duration_min': durations.get(vid_id, 0),
                    'position':     item['snippet']['position'],
                })

        if progress_cb:
            progress_cb(f'Sayfa {page} · {len(videos)} video')

        next_page_token = items_resp.get('nextPageToken')
        if not next_page_token:
            break

    elapsed = time.monotonic() - start
    logger.info('YouTube fetch done: %s, %d videos, %d pages, %.1fs', playlist_id, len(videos), page, elapsed)
    return videos


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_playlist_meta(playlist_id: str) -> dict:
    """
    Returns {title, channel_title, video_count}.
    Raises PlaylistNotFound or YouTubeAPIError on failure.
    """
    try:
        yt = _build_youtube()
        resp = yt.playlists().list(
            part='snippet,contentDetails',
            id=playlist_id,
        ).execute(num_retries=2)
    except HttpError as exc:
        _log_http_error(exc, playlist_id)
        raise YouTubeAPIError(_http_error_to_user_msg(exc)) from exc
    except (socket.timeout, TimeoutError, httplib2.ServerNotFoundError) as exc:
        logger.error('YouTube timeout (meta) for %s: %s', playlist_id, exc)
        raise YouTubeAPIError('YouTube yanıt vermiyor, lütfen tekrar deneyin.') from exc

    items = resp.get('items', [])
    if not items:
        raise PlaylistNotFound(playlist_id)

    snippet = items[0]['snippet']
    count = items[0].get('contentDetails', {}).get('itemCount', 0)
    return {
        'title':         snippet['title'],
        'channel_title': snippet.get('channelTitle', ''),
        'video_count':   count,
    }


def sync_playlist(
    playlist_id: str,
    subject,
    exam_type: str,
    imported_by,
    progress_cb=None,
) -> dict:
    """
    Fetch all pages outside any transaction, then sync in one short atomic block.
    Returns {playlist_pk, summary}.
    Raises PlaylistNotFound or YouTubeAPIError on failure.
    """
    from django.utils import timezone
    from tasks_app.models import YouTubePlaylist, YouTubeVideo

    if progress_cb:
        progress_cb('Meta alınıyor…')

    yt = _build_youtube()
    meta = fetch_playlist_meta(playlist_id)

    if progress_cb:
        progress_cb('Videolar alınıyor…')

    fetched = _fetch_all_pages(yt, playlist_id, progress_cb)

    if progress_cb:
        progress_cb('Kaydediliyor…')

    with transaction.atomic():
        playlist_obj, _ = YouTubePlaylist.objects.update_or_create(
            playlist_id=playlist_id,
            imported_by=imported_by,
            defaults={
                'title':         meta['title'],
                'channel_title': meta['channel_title'],
                'subject':       subject,
                'exam_type':     exam_type,
            },
        )

        existing = {v.video_id: v for v in playlist_obj.videos.all()}
        fetched_vid_ids = {item['video_id'] for item in fetched}

        to_create: list[YouTubeVideo] = []
        to_update: list[YouTubeVideo] = []

        for item in fetched:
            vid_id = item['video_id']
            if vid_id in existing:
                v = existing[vid_id]
                v.title        = item['title']
                v.duration_min = item['duration_min']
                v.position     = item['position']
                to_update.append(v)
            else:
                to_create.append(YouTubeVideo(
                    playlist=playlist_obj,
                    video_id=vid_id,
                    title=item['title'],
                    duration_min=item['duration_min'],
                    position=item['position'],
                ))

        removed_vid_ids = set(existing) - fetched_vid_ids
        removed_pks = {existing[vid].pk for vid in removed_vid_ids}

        removed_count = 0
        if removed_pks:
            referenced = _find_referenced_video_pks(playlist_obj.pk)
            deletable = removed_pks - referenced
            if deletable:
                YouTubeVideo.objects.filter(pk__in=deletable).delete()
            removed_count = len(deletable)

        if to_update:
            YouTubeVideo.objects.bulk_update(to_update, ['title', 'duration_min', 'position'])

        if to_create:
            YouTubeVideo.objects.bulk_create(to_create, ignore_conflicts=True)

        playlist_obj.last_synced_at = timezone.now()
        playlist_obj.save(update_fields=['last_synced_at', 'updated_at'])

    summary = f'{len(to_create)} yeni, {len(to_update)} güncellendi, {removed_count} kaldırıldı'
    return {'playlist_pk': playlist_obj.pk, 'summary': summary}

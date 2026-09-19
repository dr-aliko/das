"""WordPress REST API integration for coach availability sync."""
import logging
import re
import unicodedata

import requests
from decouple import config

logger = logging.getLogger(__name__)

WP_API_BASE = 'https://vagus.tr/wp-json/wp/v2'
WP_API_USER = config('WP_API_USER', default='')
WP_API_PASSWORD = config('WP_API_PASSWORD', default='')
_TIMEOUT = 10


def _auth():
    return (WP_API_USER, WP_API_PASSWORD) if WP_API_USER else None


def _tr_slugify(text):
    """Slugify a Turkish name the same way WordPress does."""
    text = text.replace('İ', 'i').replace('I', 'i')
    tr_map = str.maketrans({
        'Ç': 'c', 'Ğ': 'g', 'Ö': 'o', 'Ş': 's', 'Ü': 'u',
        'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
    })
    text = text.translate(tr_map)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def fetch_all_wp_coaches():
    """Return a list of all koclar WP posts [{id, title, slug, acf}, ...]."""
    posts = []
    page = 1
    while True:
        try:
            resp = requests.get(
                f'{WP_API_BASE}/koclar',
                params={'per_page': 100, 'page': page},
                auth=_auth(),
                timeout=_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.error('WP fetch_all_wp_coaches failed: %s', exc)
            break
        if resp.status_code == 400:
            break
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        posts.extend(batch)
        total_pages = int(resp.headers.get('X-WP-TotalPages', 1))
        if page >= total_pages:
            break
        page += 1
    return posts


def suggest_wp_matches(coaches):
    """
    Returns a dict:
      {
        'suggested': [{'coach': User, 'wp': {id, title, slug}}, ...],
        'unmatched_coaches': [User, ...],   # no confident WP match
        'unmatched_wp': [{id, title, slug}, ...]  # WP posts with no Django coach
      }
    """
    wp_posts = fetch_all_wp_coaches()
    wp_by_slug = {p['slug']: p for p in wp_posts}

    suggested = []
    unmatched_coaches = []
    matched_wp_slugs = set()

    for coach in coaches:
        if coach.wordpress_post_id is not None:
            continue  # already linked
        slug = _tr_slugify(coach.full_name)
        wp = wp_by_slug.get(slug)
        if wp:
            suggested.append({'coach': coach, 'wp': wp})
            matched_wp_slugs.add(slug)
        else:
            unmatched_coaches.append(coach)

    unmatched_wp = [p for p in wp_posts if p['slug'] not in matched_wp_slugs]

    return {
        'suggested': suggested,
        'unmatched_coaches': unmatched_coaches,
        'unmatched_wp': unmatched_wp,
    }


def update_wp_coach_availability(wordpress_post_id, is_available):
    """
    POST {"acf": {"musaitlik": is_available}} to WP.
    Returns (True, None) on success or (False, error_message) on failure.
    """
    if not WP_API_USER:
        return False, 'WP API kimlik bilgileri yapılandırılmamış.'
    try:
        resp = requests.post(
            f'{WP_API_BASE}/koclar/{wordpress_post_id}',
            json={'acf': {'musaitlik': is_available}},
            auth=_auth(),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return True, None
    except requests.HTTPError as exc:
        logger.error('WP availability update HTTP error (post %s): %s', wordpress_post_id, exc)
        return False, 'Web sitesi güncellenemedi, tekrar deneyin.'
    except requests.RequestException as exc:
        logger.error('WP availability update network error (post %s): %s', wordpress_post_id, exc)
        return False, 'Web sitesine ulaşılamadı, tekrar deneyin.'

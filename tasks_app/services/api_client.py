import hashlib
import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_BASE = getattr(settings, "EXTERNAL_API_BASE_URL", "http://152.70.23.159:5000/api")
_TIMEOUT = getattr(settings, "EXTERNAL_API_TIMEOUT", 5)
_CACHE_TTL = 300  # 5 minutes


def _get(url: str, params: dict | None = None):
    raw_key = f"{url}:{sorted(params.items()) if params else ''}"
    cache_key = "api:" + hashlib.md5(raw_key.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, params=params, timeout=_TIMEOUT)
        logger.info("External API %s → HTTP %s", url, r.status_code)
        r.raise_for_status()
        data = r.json()
        cache.set(cache_key, data, _CACHE_TTL)
        return data
    except requests.RequestException as exc:
        logger.warning("External API request failed [%s]: %s", url, exc)
        return None
    except ValueError as exc:
        logger.warning("External API returned invalid JSON [%s]: %s", url, exc)
        return None


def _extract_list(data, *envelope_keys: str) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in envelope_keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
        logger.warning(
            "External API dict had none of keys %s: got %r", envelope_keys, list(data.keys())
        )
    return []


def get_dersler() -> list:
    data = _get(f"{_BASE}/dersler")
    items = _extract_list(data, "dersler", "data", "results")
    if not items:
        logger.warning("get_dersler: returned empty — raw type was %s", type(data).__name__)
        return []
    return [{"id": d["Id"], "ad": d["Title"]} for d in items if "Id" in d]


def get_oynatma_listeleri(ders_id: int, sinav_tipi: str) -> list:
    data = _get(f"{_BASE}/oynatma-listeleri/{ders_id}", params={"tip": sinav_tipi})
    items = _extract_list(data, "listeler", "data", "results")
    return [{"id": d["Id"], "baslik": d["Title"]} for d in items if "Id" in d]


def get_videolar(liste_id: int) -> list:
    data = _get(f"{_BASE}/videolar/{liste_id}")
    items = _extract_list(data, "videolar", "data", "results")
    return [{"id": d["Id"], "baslik": d["Title"], "sure_dk": d["Sure_dk"]} for d in items if "Id" in d]

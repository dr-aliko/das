import hashlib
import logging

from django.contrib import admin
from django.core.cache import cache
from django.http import HttpResponse

from users_app.utils import client_ip

logger = logging.getLogger(__name__)

_WINDOW   = 900   # 15-minute fixed window and lockout duration
_PAIR_MAX = 10    # failures for username+IP before lockout
_IP_MAX   = 20    # failures for IP across all accounts before lockout
_MSG = (
    'Çok fazla başarısız giriş denemesi. '
    'Lütfen 15 dakika sonra tekrar deneyin.'
)


def _cache_keys(username, ip):
    pair = hashlib.md5(f'{username}|{ip}'.encode()).hexdigest()
    iph  = hashlib.md5(ip.encode()).hexdigest()
    return f'admin_pair_{pair}', f'admin_ip_{iph}'


def _is_limited(username, ip):
    pk, ik = _cache_keys(username, ip)
    return (cache.get(pk) or 0) >= _PAIR_MAX or (cache.get(ik) or 0) >= _IP_MAX


def _increment(username, ip):
    pk, ik = _cache_keys(username, ip)
    for key in (pk, ik):
        cache.set(key, (cache.get(key) or 0) + 1, _WINDOW)


def _clear(username, ip):
    pk, ik = _cache_keys(username, ip)
    cache.delete(pk)
    cache.delete(ik)


def admin_login_view(request, extra_context=None):
    if request.method != 'POST':
        return admin.site.login(request, extra_context=extra_context)

    username = request.POST.get('username', '').strip()
    ip = client_ip(request)

    try:
        if _is_limited(username, ip):
            return HttpResponse(
                _MSG, content_type='text/plain; charset=utf-8', status=429
            )
    except Exception:
        logger.warning('admin login rate-limit check failed; allowing the attempt', exc_info=True)

    response = admin.site.login(request, extra_context=extra_context)

    try:
        if response.status_code in (301, 302):
            _clear(username, ip)
        else:
            _increment(username, ip)
    except Exception:
        logger.warning('admin login rate-limit bookkeeping failed', exc_info=True)

    return response

import hashlib
import secrets

from django.core.cache import cache

_CODE_EXPIRY      = 600   # 10 minutes
_MAX_ATTEMPTS     = 5
_RESEND_COOLDOWN  = 120   # 2 minutes
_RESEND_WINDOW    = 1800  # 30 minutes
_RESEND_MAX       = 5

OK            = 'OK'
WRONG         = 'WRONG'
NO_CODE       = 'NO_CODE'
MAX_ATTEMPTS  = 'MAX_ATTEMPTS'


def _keys(session_key, email):
    h = hashlib.sha256(f'{session_key}|{email.lower()}'.encode()).hexdigest()
    return (
        f'pv_code_{h}',       # stores hashed code
        f'pv_att_{h}',        # attempt counter
        f'pv_cool_{h}',       # resend cooldown flag
        f'pv_rcnt_{h}',       # resend count in window
    )


def _hash_code(code):
    return hashlib.sha256(code.encode()).hexdigest()


def issue_code(session_key, email):
    """Generate a 6-digit code, store hashed, return plaintext."""
    code_key, att_key, _, _ = _keys(session_key, email)
    code = f'{secrets.randbelow(1_000_000):06d}'
    cache.set(code_key, _hash_code(code), _CODE_EXPIRY)
    cache.delete(att_key)
    return code


def verify(session_key, email, submitted):
    """
    Returns one of: OK, WRONG, NO_CODE, MAX_ATTEMPTS.
    On OK the code is deleted (single-use).
    """
    code_key, att_key, _, _ = _keys(session_key, email)

    attempts = cache.get(att_key) or 0
    if attempts >= _MAX_ATTEMPTS:
        return MAX_ATTEMPTS

    stored_hash = cache.get(code_key)
    if stored_hash is None:
        return NO_CODE

    if stored_hash == _hash_code(submitted.strip()):
        cache.delete(code_key)
        cache.delete(att_key)
        return OK

    new_attempts = attempts + 1
    cache.set(att_key, new_attempts, _CODE_EXPIRY)
    if new_attempts >= _MAX_ATTEMPTS:
        return MAX_ATTEMPTS
    return WRONG


def can_resend(session_key, email):
    """True if neither cooldown nor window limit is active."""
    _, _, cool_key, rcnt_key = _keys(session_key, email)
    if cache.get(cool_key):
        return False
    cnt = cache.get(rcnt_key) or 0
    return cnt < _RESEND_MAX


def record_resend(session_key, email):
    """Mark a resend: set cooldown, increment window counter."""
    _, _, cool_key, rcnt_key = _keys(session_key, email)
    cache.set(cool_key, 1, _RESEND_COOLDOWN)
    try:
        cache.incr(rcnt_key)
    except ValueError:
        cache.set(rcnt_key, 1, _RESEND_WINDOW)

"""
Panel work-item counters.  Call all_badges() once per staff request.

Counter (g) — coaches with no free capacity — is intentionally omitted:
computing it requires a 3-table join with date-filtered aggregation over
CoachCapacityGrant and CoachStudent for every coach.  That is not a cheap
single query, so it is skipped per spec.
"""
from datetime import date

from django.core.cache import cache

_TTL = 60  # seconds


def _safe(key, fn):
    """Return fn() cached for _TTL s.  Any cache or query failure → 0."""
    try:
        val = cache.get(key)
        if val is not None:
            return val
    except Exception:
        pass
    try:
        val = fn()
        try:
            cache.set(key, val, _TTL)
        except Exception:
            pass
        return val
    except Exception:
        return 0


# ── Individual counter functions ──────────────────────────────────────────────

def _docs():
    from users_app.models import CoachProfile
    return (CoachProfile.objects
            .filter(document_status=CoachProfile.DOC_PENDING)
            .exclude(document='').exclude(document=None)
            .count())


def _transfers_purchase():
    from purchase_app.models import Order
    return Order.objects.filter(status=Order.STATUS_AWAITING_TRANSFER).count()


def _transfers_capacity():
    from capacity_app.models import CoachCapacityOrder
    return CoachCapacityOrder.objects.filter(
        status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
    ).count()


def _earnings():
    from earnings_app.models import EarningRow
    return EarningRow.objects.filter(
        status__in=[EarningRow.STATUS_RELEASED, EarningRow.STATUS_APPROVED],
    ).count()


def _no_iban():
    from django.db.models import Q
    from users_app.models import User
    return (User.objects
            .filter(role='coach', is_active=True, is_approved=True)
            .filter(Q(coach_profile__isnull=True) | Q(coach_profile__iban=''))
            .count())


def _no_wp():
    from users_app.models import User
    return User.objects.filter(
        role='coach', is_active=True, is_approved=True,
        wordpress_post_id__isnull=True,
    ).count()


def _overdue():
    from users_app.models import CoachStudent
    return CoachStudent.objects.filter(
        source=CoachStudent.SOURCE_VAGUS,
        active=True,
        next_payment_due__lt=date.today(),
    ).count()


# ── Public API ────────────────────────────────────────────────────────────────

def all_badges():
    """Compute (or serve from 60-s cache) every panel counter.  Always returns
    a dict with int values; any failure falls back to 0 for that counter."""
    docs       = _safe('pbadge:docs',         _docs)
    t_purchase = _safe('pbadge:transfers_p',  _transfers_purchase)
    t_capacity = _safe('pbadge:transfers_c',  _transfers_capacity)
    earnings   = _safe('pbadge:earnings',     _earnings)
    no_iban    = _safe('pbadge:no_iban',      _no_iban)
    no_wp      = _safe('pbadge:no_wp',        _no_wp)
    overdue    = _safe('pbadge:overdue',      _overdue)

    transfers = t_purchase + t_capacity

    return {
        # Raw counters
        'docs':               docs,
        'transfers_purchase': t_purchase,
        'transfers_capacity': t_capacity,
        'transfers':          transfers,
        'earnings':           earnings,
        'no_iban':            no_iban,
        'no_wp':              no_wp,
        'overdue':            overdue,
        # Per-page second-row badge values
        'belgeler':           docs + no_iban,   # Belgeler page
        # Group-level pill badge rollups
        'koclar':             docs + no_iban + no_wp,
        'ogrenciler_group':   overdue,
        'satis':              transfers,
        'odemeler_group':     earnings,
        # Home-page helper
        'any_pending': bool(docs + no_iban + no_wp + transfers + earnings + overdue),
    }

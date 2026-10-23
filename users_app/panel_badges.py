"""
Panel work-item counters.  Call all_badges() once per staff request.

Counter (g) — coaches with no free capacity — is intentionally omitted:
computing it requires a 3-table join with date-filtered aggregation over
CoachCapacityGrant and CoachStudent for every coach.  That is not a cheap
single query, so it is skipped per spec.

Each qs_*() function returns the queryset that both the badge counter and
the matching filtered list view use, so the count can never disagree with
the list.
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


# ── Shared queryset functions ─────────────────────────────────────────────────

def qs_docs():
    from users_app.models import CoachProfile
    return (CoachProfile.objects
            .select_related('user', 'document_reviewed_by')
            .filter(document_status=CoachProfile.DOC_PENDING)
            .exclude(document='').exclude(document=None)
            .order_by('-updated_at'))


def qs_transfers_purchase():
    from purchase_app.models import Order
    return (Order.objects
            .select_related('coach', 'student', 'plan')
            .filter(status=Order.STATUS_AWAITING_TRANSFER))


def qs_transfers_capacity():
    """Claimed capacity orders awaiting staff approval (coach has notified payment)."""
    from capacity_app.models import CoachCapacityOrder
    return (CoachCapacityOrder.objects
            .select_related('coach')
            .filter(
                status=CoachCapacityOrder.STATUS_AWAITING_TRANSFER,
                payment_claimed_at__isnull=False,
            )
            .order_by('-payment_claimed_at'))


def qs_earnings():
    from earnings_app.models import EarningRow
    return (EarningRow.objects
            .select_related('coach', 'student', 'order', 'order__plan', 'manual_record')
            .filter(status__in=[EarningRow.STATUS_RELEASED, EarningRow.STATUS_APPROVED])
            .order_by('-coverage_start', '-created_at'))


def qs_no_iban():
    from django.db.models import Q
    from users_app.models import User
    return (User.objects
            .select_related('coach_profile')
            .filter(role='coach', is_active=True, is_approved=True)
            .filter(Q(coach_profile__isnull=True) | Q(coach_profile__iban=''))
            .order_by('full_name'))


def qs_no_phone():
    from django.db.models import Q
    from users_app.models import User
    return (User.objects
            .select_related('coach_profile')
            .filter(role='coach', is_active=True, is_approved=True)
            .filter(Q(coach_profile__isnull=True)
                    | Q(coach_profile__phone='')
                    | Q(coach_profile__phone__isnull=True))
            .order_by('full_name'))


def qs_doc_missing():
    """Approved active coaches who have not uploaded any document."""
    from users_app.models import CoachProfile, User
    approved_ids = (CoachProfile.objects
                    .filter(document_status=CoachProfile.DOC_APPROVED, document__gt='')
                    .values_list('user_id', flat=True))
    return (User.objects
            .select_related('coach_profile')
            .filter(role='coach', is_active=True, is_approved=True)
            .exclude(pk__in=approved_ids)
            .order_by('full_name'))


def qs_no_wp():
    from users_app.models import User
    return (User.objects
            .filter(role='coach', is_active=True, is_approved=True,
                    wordpress_post_id__isnull=True)
            .order_by('full_name'))


def qs_profile_issues():
    """Coaches with any profile issue: no phone, no IBAN, or non-approved/missing document."""
    from django.db.models import Q
    from users_app.models import CoachProfile, User
    unapproved_doc_ids = (CoachProfile.objects
                          .exclude(document_status=CoachProfile.DOC_APPROVED)
                          .exclude(document='').exclude(document=None)
                          .values_list('user_id', flat=True))
    return (User.objects
            .select_related('coach_profile')
            .filter(role='coach', is_active=True, is_approved=True)
            .filter(
                Q(coach_profile__isnull=True)
                | Q(coach_profile__iban='')
                | Q(coach_profile__phone='') | Q(coach_profile__phone__isnull=True)
                | Q(coach_profile__document='') | Q(coach_profile__document__isnull=True)
                | Q(pk__in=unapproved_doc_ids)
            )
            .distinct()
            .order_by('full_name'))


def qs_overdue():
    from users_app.models import CoachStudent
    return (CoachStudent.objects
            .select_related('student', 'coach')
            .filter(source=CoachStudent.SOURCE_VAGUS, active=True,
                    next_payment_due__lt=date.today())
            .order_by('next_payment_due'))


def qs_renewal_orders_claimed():
    """CoachStudentRenewalOrders that have been claimed (payment notified) but not yet approved."""
    from capacity_app.models import CoachStudentRenewalOrder
    return (CoachStudentRenewalOrder.objects
            .select_related('coach_student__coach', 'coach_student__student')
            .filter(
                status=CoachStudentRenewalOrder.STATUS_AWAITING_TRANSFER,
                payment_claimed_at__isnull=False,
            )
            .order_by('-payment_claimed_at'))


# ── Individual counter functions ──────────────────────────────────────────────

def _docs():
    return qs_docs().count()


def _transfers_purchase():
    return qs_transfers_purchase().count()


def _transfers_capacity():
    return qs_transfers_capacity().count()


def _earnings():
    return qs_earnings().count()


def _no_iban():
    return qs_no_iban().count()


def _no_wp():
    return qs_no_wp().count()


def _overdue():
    return qs_overdue().count()


def _belgeler():
    return qs_profile_issues().count()


def _renewals_claimed():
    return qs_renewal_orders_claimed().count()


# ── Public API ────────────────────────────────────────────────────────────────

def all_badges():
    """Compute (or serve from 60-s cache) every panel counter.  Always returns
    a dict with int values; any failure falls back to 0 for that counter."""
    docs            = _safe('pbadge:docs',            _docs)
    t_purchase      = _safe('pbadge:transfers_p',     _transfers_purchase)
    t_capacity      = _safe('pbadge:transfers_c',     _transfers_capacity)
    earnings        = _safe('pbadge:earnings',        _earnings)
    no_iban         = _safe('pbadge:no_iban',         _no_iban)
    no_wp           = _safe('pbadge:no_wp',           _no_wp)
    overdue         = _safe('pbadge:overdue',         _overdue)
    belgeler        = _safe('pbadge:belgeler',        _belgeler)
    renewals_claimed = _safe('pbadge:renewals_claimed', _renewals_claimed)

    # Capacity claimed is distinct from the purchase-order sales badge
    transfers = t_purchase

    return {
        # Raw counters
        'docs':                docs,
        'transfers_purchase':  t_purchase,
        'transfers_capacity':  t_capacity,
        'transfers':           transfers,
        'earnings':            earnings,
        'no_iban':             no_iban,
        'no_wp':               no_wp,
        'overdue':             overdue,
        'renewals_claimed':    renewals_claimed,
        # Per-page second-row badge values
        'belgeler':            belgeler,
        # Group-level pill badge rollups
        'koclar':              belgeler + no_wp + t_capacity,
        'ogrenciler_group':    overdue,
        'satis':               transfers,
        'odemeler_group':      earnings,
        # Home-page helper
        'any_pending': bool(belgeler + no_wp + t_capacity + transfers + earnings + overdue + renewals_claimed),
    }

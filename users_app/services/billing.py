from datetime import date
from decimal import Decimal

from django.db.models import Q

from ..models import CoachStudent, FeeTier


def _lookup_fee(source: str, count: int):
    """Return (fee: Decimal, undefined: bool) for the given source and student count."""
    if count == 0:
        return Decimal('0'), False
    tier = (
        FeeTier.objects
        .filter(source=source, min_students__lte=count)
        .filter(Q(max_students__isnull=True) | Q(max_students__gte=count))
        .order_by('order')
        .first()
    )
    if tier is None:
        return None, True
    return tier.monthly_fee_try, False


def coach_billing_summary(coach) -> dict:
    """
    Returns live billing state for a coach.

    Keys:
      vagus_students      list of {link, days_remaining}
      coach_students      list of {link}
      unclassified        list of {link}
      vagus_count / coach_count / unclassified_count
      vagus_fee           Decimal or None (None = no matching tier)
      coach_fee           Decimal or None
      total_fee           Decimal or None (sum; None if either is undefined when count > 0)
      monthly_fee         alias of total_fee for backward compat
      vagus_fee_undefined bool
      coach_fee_undefined bool
      warning_count       vagus students with payment overdue or due within 7 days
      current_vagus_tier  FeeTier instance matching current vagus count, or None
      vagus_tiers         ordered queryset of all vagus FeeTier rows (for legend)
    """
    links = (
        CoachStudent.objects
        .filter(coach=coach, active=True, student__is_active=True)
        .select_related('student')
        .order_by('student__full_name')
    )

    vagus_students = []
    coach_students = []
    unclassified = []
    warning_count = 0
    today = date.today()

    for link in links:
        if link.source == CoachStudent.SOURCE_VAGUS:
            days = (link.next_payment_due - today).days if link.next_payment_due else None
            if days is not None and days <= 7:
                warning_count += 1
            vagus_students.append({'link': link, 'days_remaining': days})
        elif link.source == CoachStudent.SOURCE_COACH:
            coach_students.append({'link': link})
        else:
            unclassified.append({'link': link})

    vagus_count = len(vagus_students)
    coach_count = len(coach_students)

    vagus_fee, vagus_fee_undefined = _lookup_fee('vagus', vagus_count)
    coach_fee, coach_fee_undefined = _lookup_fee('coach', coach_count)

    if vagus_fee is not None and coach_fee is not None:
        total_fee = vagus_fee + coach_fee
    else:
        total_fee = None

    vagus_tiers = list(FeeTier.objects.filter(source='vagus').order_by('order'))
    coach_tiers = list(FeeTier.objects.filter(source='coach').order_by('order'))

    def _find_active_tier(tiers, count):
        if count == 0:
            return None
        for tier in tiers:
            max_ok = tier.max_students is None or tier.max_students >= count
            if tier.min_students <= count and max_ok:
                return tier
        return None

    current_vagus_tier = _find_active_tier(vagus_tiers, vagus_count)
    current_coach_tier = _find_active_tier(coach_tiers, coach_count)

    return {
        'vagus_students': vagus_students,
        'coach_students': coach_students,
        'unclassified': unclassified,
        'vagus_count': vagus_count,
        'coach_count': coach_count,
        'unclassified_count': len(unclassified),
        'vagus_fee': vagus_fee,
        'coach_fee': coach_fee,
        'total_fee': total_fee,
        'monthly_fee': total_fee,  # backward-compat alias
        'vagus_fee_undefined': vagus_fee_undefined,
        'coach_fee_undefined': coach_fee_undefined,
        'warning_count': warning_count,
        'current_vagus_tier': current_vagus_tier,
        'vagus_tiers': vagus_tiers,
        'current_coach_tier': current_coach_tier,
        'coach_tiers': coach_tiers,
    }

from datetime import date

from ..models import CoachStudent

# Monthly fee in TL per number of Vagus-sourced active students.
# Each band applies up to (and including) the given count.
_FEE_BANDS = [
    (0,   0),
    (3,  150),
    (7,  300),
    (float('inf'), 500),
]


def _monthly_fee(vagus_count: int) -> int:
    for threshold, fee in _FEE_BANDS:
        if vagus_count <= threshold:
            return fee
    return _FEE_BANDS[-1][1]


def coach_billing_summary(coach) -> dict:
    """
    Returns live billing state for a coach:
      vagus_students  — list of {link, days_remaining} for source='vagus' active students
      coach_students  — list of {link} for source='coach' active students
      unclassified    — list of {link} for source=NULL active students
      monthly_fee     — int TL based on vagus_count tier
      warning_count   — vagus students with payment overdue or due within 7 days
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

    return {
        'vagus_students': vagus_students,
        'coach_students': coach_students,
        'unclassified': unclassified,
        'vagus_count': len(vagus_students),
        'coach_count': len(coach_students),
        'unclassified_count': len(unclassified),
        'monthly_fee': _monthly_fee(len(vagus_students)),
        'warning_count': warning_count,
    }

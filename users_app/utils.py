from django.utils import timezone


def tr_lower(s):
    """Turkish-aware lowercase: İ→i, I→ı before Python .lower()."""
    return s.replace('İ', 'i').replace('I', 'ı').lower()


def all_coaches_for_json():
    """Return [{id, name, email}] list of all active coaches for json_script."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return [
        {'id': c.pk, 'name': c.full_name, 'email': c.email}
        for c in User.objects.filter(role='coach', is_active=True).order_by('full_name')
    ]


def filter_coaches_by_q(coaches, q):
    """Return coaches whose full_name or email contains q (Turkish-case-insensitive)."""
    if not q:
        return coaches
    q_lc = tr_lower(q)
    return [c for c in coaches if q_lc in tr_lower(c.full_name) or q_lc in tr_lower(c.email)]


def membership_expiry_info(cs):
    """
    Returns expiry display info for a CoachStudent, or None if no badge should show.

    Vagus-sourced students with a set next_payment_due always get a badge (unchanged).

    When COACH_PER_STUDENT_PERIODS is True, coach-own students also get the same
    badge when next_payment_due is set.  "Own student" is determined by the shared
    is_own_student_source rule: source=='coach' → own; source=='vagus' → not own;
    NULL source → own UNLESS the student has a paid purchase_app Order (legacy links
    created before the source field was added default to own-student behaviour unless
    evidence of a Vagus purchase exists).

    Any error in the new code path returns None (fail-open).
    """
    from users_app.models import CoachStudent
    if cs.source != CoachStudent.SOURCE_VAGUS:
        try:
            from django.conf import settings
            if not getattr(settings, 'COACH_PER_STUDENT_PERIODS', False):
                return None
            from capacity_app.services import is_own_student_source
            if not is_own_student_source(cs.source, cs.student):
                return None
            # own student with flag on — fall through to the shared badge logic
        except Exception:
            return None

    if cs.next_payment_due is None:
        return None
    today = timezone.localdate()
    days = (cs.next_payment_due - today).days
    title = cs.next_payment_due.strftime('%d.%m.%Y')
    if days < 0:
        return {
            'days': days,
            'label': f'Süre bitti ({abs(days)} gün önce)',
            'variant': 'danger',
            'title': title,
            'expired': True,
        }
    if days == 0:
        return {
            'days': 0,
            'label': 'Bugün bitiyor',
            'variant': 'danger',
            'title': title,
            'expired': False,
        }
    if days <= 3:
        return {
            'days': days,
            'label': f'{days} gün kaldı',
            'variant': 'danger',
            'title': title,
            'expired': False,
        }
    if days <= 14:
        return {
            'days': days,
            'label': f'{days} gün kaldı',
            'variant': 'warn',
            'title': title,
            'expired': False,
        }
    return {
        'days': days,
        'label': f'{days} gün kaldı',
        'variant': 'success',
        'title': title,
        'expired': False,
    }


def is_student_program_expired(coach, student_id):
    """
    Returns True only when coach's active student has next_payment_due < today AND
    the expiry rule applies to them.

    Expiry rule applies to:
    - Vagus-sourced students (always, unchanged behaviour).
    - Coach-own students when COACH_PER_STUDENT_PERIODS is True.
      "Own student" = is_own_student_source(source, student): source=='coach' → True;
      source=='vagus' → False; NULL source → True unless a paid purchase Order exists
      (same rule as capacity slot counting).

    Returns False in every other case, including unexpected exceptions (fail open).
    """
    import logging
    try:
        from users_app.models import CoachStudent
        try:
            cs = CoachStudent.objects.get(coach=coach, student_id=student_id, active=True)
        except CoachStudent.DoesNotExist:
            return False

        if cs.source != CoachStudent.SOURCE_VAGUS:
            from django.conf import settings
            if not getattr(settings, 'COACH_PER_STUDENT_PERIODS', False):
                return False
            from capacity_app.services import is_own_student_source
            if not is_own_student_source(cs.source, cs.student):
                return False

        if cs.next_payment_due is None:
            return False
        return cs.next_payment_due < timezone.localdate()
    except Exception as exc:
        logging.getLogger(__name__).warning(
            'is_student_program_expired: unexpected error (coach=%s, student_id=%s): %s',
            coach, student_id, exc,
        )
        return False

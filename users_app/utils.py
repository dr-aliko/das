from django.utils import timezone


def membership_expiry_info(cs):
    """
    Returns expiry display info for a CoachStudent, or None if no badge should show.
    Only Vagus-sourced students with a set next_payment_due get a badge.
    """
    from users_app.models import CoachStudent
    if cs.source != CoachStudent.SOURCE_VAGUS:
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
    Returns True only when coach's active Vagus-sourced student has next_payment_due < today.
    Returns False for every other case, including unexpected exceptions (fail open).
    """
    import logging
    try:
        from users_app.models import CoachStudent
        try:
            cs = CoachStudent.objects.get(coach=coach, student_id=student_id, active=True)
        except CoachStudent.DoesNotExist:
            return False
        if cs.source != CoachStudent.SOURCE_VAGUS:
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

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
            'variant': 'expired',
            'title': title,
            'expired': True,
        }
    if days == 0:
        return {
            'days': 0,
            'label': 'Bugün bitiyor',
            'variant': 'warning',
            'title': title,
            'expired': False,
        }
    if days <= 7:
        return {
            'days': days,
            'label': f'{days} gün kaldı',
            'variant': 'warning',
            'title': title,
            'expired': False,
        }
    return {
        'days': days,
        'label': f'{days} gün kaldı',
        'variant': 'normal',
        'title': title,
        'expired': False,
    }


def is_student_program_expired(coach, student_id):
    """
    Returns True if this coach's Vagus-sourced student has an expired membership.
    Returns False for coach-source, null-source, or missing CoachStudent records.
    """
    from users_app.models import CoachStudent
    try:
        cs = CoachStudent.objects.get(coach=coach, student_id=student_id, active=True)
    except CoachStudent.DoesNotExist:
        return False
    if cs.source != CoachStudent.SOURCE_VAGUS:
        return False
    if cs.next_payment_due is None:
        return False
    today = timezone.localdate()
    return cs.next_payment_due < today

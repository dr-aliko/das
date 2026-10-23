import logging

_log = logging.getLogger(__name__)


def cancel_stale_capacity_orders_task():
    from .services import cancel_stale_capacity_orders
    return cancel_stale_capacity_orders()


def notify_expiring_grants_task():
    from django.conf import settings
    if getattr(settings, 'COACH_PER_STUDENT_PERIODS', False):
        return 0
    from .services import notify_expiring_grants
    return notify_expiring_grants()


def notify_expiring_student_periods_task():
    from django.conf import settings
    if not getattr(settings, 'COACH_PER_STUDENT_PERIODS', False):
        return 0
    from .services import notify_expiring_student_periods
    return notify_expiring_student_periods()

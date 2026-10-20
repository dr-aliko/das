import logging

_log = logging.getLogger(__name__)


def cancel_stale_capacity_orders_task():
    from .services import cancel_stale_capacity_orders
    return cancel_stale_capacity_orders()


def notify_expiring_grants_task():
    from .services import notify_expiring_grants
    return notify_expiring_grants()

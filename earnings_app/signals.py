import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

_log = logging.getLogger(__name__)

_VOID_STATUSES = {'cancelled', 'refunded'}


@receiver(post_save, sender='purchase_app.Order')
def order_status_changed(sender, instance, **kwargs):
    if instance.status in _VOID_STATUSES:
        try:
            from django.db import transaction
            from .services import void_order_earnings
            with transaction.atomic():
                void_order_earnings(instance.pk, reason=f'order_{instance.status}')
        except Exception:
            _log.exception('earnings: void_order_earnings failed for order %s', instance.pk)

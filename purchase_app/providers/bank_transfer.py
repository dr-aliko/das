import secrets

from django.urls import reverse

from .base import BaseProvider

# Unambiguous: A-Z minus O, I, L; digits 2-9 (no 0, 1)
_REF_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def _generate_ref():
    return 'VG-' + ''.join(secrets.choice(_REF_ALPHABET) for _ in range(6))


class BankTransferProvider(BaseProvider):
    name = 'bank_transfer'

    def __init__(self, iban, holder, bank_name):
        self.iban      = iban
        self.holder    = holder
        self.bank_name = bank_name

    def create_checkout(self, order, request=None):
        from django.db import transaction
        from django_q.tasks import async_task
        from purchase_app.models import Order

        # Generate unique ref, regenerate on collision
        while True:
            ref = _generate_ref()
            if not Order.objects.filter(provider_ref=ref).exists():
                break

        Order.objects.filter(pk=order.pk).update(
            provider_ref=ref,
            status=Order.STATUS_AWAITING_TRANSFER,
        )
        order.provider_ref = ref
        order.status = Order.STATUS_AWAITING_TRANSFER

        order_pk = order.pk
        transaction.on_commit(
            lambda: async_task(
                'purchase_app.tasks.send_bank_transfer_pending_email', order_pk
            )
        )
        transaction.on_commit(
            lambda: async_task(
                'purchase_app.tasks.notify_staff_new_transfer', order_pk
            )
        )

        return reverse(
            'purchase:bank_transfer_instructions',
            kwargs={'order_token': str(order.token)},
        )

    def cancel(self, order):
        return True

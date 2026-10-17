from django.urls import reverse

from .base import BaseProvider


class SandboxProvider(BaseProvider):
    name = 'sandbox'

    def create_checkout(self, order, request=None):
        order.provider_ref = f'sandbox-{order.token}'
        order.save(update_fields=['provider_ref'])
        return reverse('purchase:sandbox_pay', kwargs={'order_token': str(order.token)})

    def cancel(self, order):
        return True

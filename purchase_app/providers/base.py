class BaseProvider:
    name = 'base'

    def create_checkout(self, order, request=None):
        """Assign order.provider_ref, save it, return redirect URL string."""
        raise NotImplementedError

    def cancel(self, order):
        """Cancel a pending order. Return bool."""
        raise NotImplementedError

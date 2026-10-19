from django.apps import AppConfig


class EarningsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'earnings_app'
    verbose_name = 'Kazançlar'

    def ready(self):
        from . import signals  # noqa

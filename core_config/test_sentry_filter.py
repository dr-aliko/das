from django.test import SimpleTestCase

from core_config.settings import _sentry_before_send


class SentryDisallowedHostFilterTests(SimpleTestCase):

    def test_disallowedhost_logger_event_is_dropped(self):
        event = {'logger': 'django.security.DisallowedHost', 'level': 'warning'}
        self.assertIsNone(_sentry_before_send(event, {}))

    def test_disallowedhost_exception_is_dropped(self):
        from django.core.exceptions import DisallowedHost
        exc = DisallowedHost('Invalid Host header')
        event = {'exception': {'values': [{'type': 'DisallowedHost'}]}}
        hint = {'exc_info': (DisallowedHost, exc, None)}
        self.assertIsNone(_sentry_before_send(event, hint))

    def test_other_exception_passes_through(self):
        event = {'exception': {'values': [{'type': 'ValueError'}]}}
        hint = {'exc_info': (ValueError, ValueError('bad value'), None)}
        result = _sentry_before_send(event, hint)
        self.assertIs(result, event)

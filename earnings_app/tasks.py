import logging

_log = logging.getLogger(__name__)


def release_held_earnings_task():
    from django.conf import settings
    from .services import release_held_earnings

    if not getattr(settings, 'COACH_EARNING_AUTO_RELEASE', True):
        _log.info('release_held_earnings_task: disabled by COACH_EARNING_AUTO_RELEASE=False')
        return 0

    released = release_held_earnings()
    return released

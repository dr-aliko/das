import logging
from unittest import mock

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client

from core_config import admin_login

LOGIN_URL = f'/{settings.ADMIN_URL_PATH}login/'
PROXY_IP = '203.0.113.77'


def _fail(client, forwarded):
    return client.post(
        LOGIN_URL,
        {'username': 'nobody', 'password': 'wrong'},
        HTTP_X_FORWARDED_FOR=forwarded,
        REMOTE_ADDR='',
    )


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_spoofed_forwarded_hop_does_not_reset_lockout():
    client = Client()
    for i in range(admin_login._PAIR_MAX):
        assert _fail(client, f'10.0.0.{i}, {PROXY_IP}').status_code == 200
    assert _fail(client, f'10.9.9.9, {PROXY_IP}').status_code == 429


@pytest.mark.django_db
def test_failure_counter_keeps_full_lockout_window():
    client = Client()
    with mock.patch.object(cache, 'set', wraps=cache.set) as spy:
        _fail(client, PROXY_IP)
        _fail(client, PROXY_IP)
    counter_calls = [c for c in spy.call_args_list if str(c.args[0]).startswith('admin_')]
    assert len(counter_calls) == 4
    assert all(c.args[2] == admin_login._WINDOW for c in counter_calls)
    pair_key, ip_key = admin_login._cache_keys('nobody', PROXY_IP)
    assert cache.get(pair_key) == 2
    assert cache.get(ip_key) == 2


@pytest.mark.django_db
def test_cache_failure_fails_open_and_is_logged(caplog):
    client = Client()
    with mock.patch.object(admin_login, '_is_limited', side_effect=RuntimeError('cache down')), \
            caplog.at_level(logging.WARNING, logger='core_config.admin_login'):
        response = _fail(client, PROXY_IP)
    assert response.status_code == 200
    assert 'rate-limit check failed' in caplog.text

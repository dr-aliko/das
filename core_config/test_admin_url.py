"""
Two tests for configurable admin URL (ADMIN_URL_PATH):
1. Admin answers on the configured path; /admin/ 404s when path is changed.
2. No admin URL path appears in anonymous or coach page HTML.
"""
from importlib import reload

import pytest
from django.test import Client, override_settings
from django.urls import clear_url_caches, reverse
from model_bakery import baker


def _reload_urlconf():
    import core_config.urls
    reload(core_config.urls)
    clear_url_caches()


@pytest.mark.django_db
def test_admin_routing_with_custom_path():
    """Admin login page is reachable at the custom path; /admin/* returns 404."""
    custom_path = 'secretadmin/'
    with override_settings(ADMIN_URL_PATH=custom_path):
        _reload_urlconf()
        c = Client()
        resp = c.get(f'/{custom_path}login/')
        assert resp.status_code == 200, (
            f'Expected admin login at /{custom_path}login/ but got {resp.status_code}'
        )
        for subpath in ('', 'login/', 'logout/'):
            resp = c.get(f'/admin/{subpath}')
            assert resp.status_code == 404, (
                f'Expected 404 at /admin/{subpath} but got {resp.status_code}'
            )
    _reload_urlconf()  # restore for subsequent tests


@pytest.mark.django_db
def test_no_admin_path_in_anon_and_coach_pages():
    """The admin URL does not appear in anonymous or coach page HTML."""
    from django.conf import settings
    admin_path = f'/{settings.ADMIN_URL_PATH}'.encode()

    c = Client()
    resp = c.get('/auth/login/')
    assert resp.status_code == 200
    assert admin_path not in resp.content, (
        f'Admin path {admin_path} leaked into anonymous login page'
    )

    from django.contrib.auth import get_user_model
    User = get_user_model()
    coach = baker.make(User, role='coach', is_active=True, is_approved=True)
    c.force_login(coach)
    resp = c.get(reverse('coach:dashboard'))
    assert resp.status_code == 200
    assert admin_path not in resp.content, (
        f'Admin path {admin_path} leaked into coach dashboard'
    )

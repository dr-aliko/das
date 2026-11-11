import re

import pytest
from django.http import HttpResponse
from django.test import Client, RequestFactory

from core_config.context_processors import DESKTOP_V2_COOKIE, V2_COOKIE
from core_config.middleware import V2CookieMiddleware


@pytest.mark.parametrize('secure', [True, False])
def test_v2_cookies_secure_only_on_secure_requests(secure):
    def view(request):
        request._set_v2_cookie = True
        request._set_desktop_v2_cookie = True
        return HttpResponse('ok')

    request = RequestFactory().get('/', secure=secure)
    response = V2CookieMiddleware(view)(request)
    assert bool(response.cookies[V2_COOKIE]['secure']) is secure
    assert bool(response.cookies[DESKTOP_V2_COOKIE]['secure']) is secure


@pytest.mark.django_db
def test_service_worker_does_not_store_navigations():
    body = Client().get('/service-worker.js').content.decode()
    assert "'vagus-shell-v2-" in body
    navigate = body.split("request.mode === 'navigate'")[1].split('Strategy 2a')[0]
    assert 'cache.put' not in navigate
    assert "caches.match('/offline/')" in navigate
    assert "'/offline/'," in body
    assert "addEventListener('push'" in body
    assert "addEventListener('notificationclick'" in body


@pytest.mark.django_db
def test_cdn_scripts_are_pinned_with_sri():
    body = Client().get('/auth/login/', follow=True).content.decode()
    from pathlib import Path
    from django.conf import settings
    templates = Path(settings.BASE_DIR) / 'templates'
    sources = [body] + [
        (templates / name).read_text(encoding='utf-8')
        for name in ('base.html', 'reports/brans_report.html', 'reports/student_exam_report.html')
    ]
    tags = [t for s in sources for t in re.findall(r'<script[^>]+cdn\.jsdelivr\.net[^>]*>', s)]
    assert len(tags) >= 5
    for tag in tags:
        assert re.search(r'@\d+\.\d+\.\d+/', tag), tag
        assert 'integrity="sha384-' in tag and 'crossorigin="anonymous"' in tag, tag

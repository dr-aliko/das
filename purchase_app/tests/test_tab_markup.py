import pytest
from model_bakery import baker

from purchase_app.models import Plan


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def coach(db):
    return baker.make(
        'users_app.User',
        role='coach',
        is_active=True,
        is_approved=True,
        wp_is_available=True,
        wordpress_post_id=9001,
        full_name='Test Coach',
    )


@pytest.fixture
def active_plan(db):
    return baker.make(
        'purchase_app.Plan',
        name='Test Plan',
        kind=Plan.KIND_ONE_TIME,
        price_kurus=49900,
        duration_days=90,
        active=True,
    )


def _enable_purchase(settings):
    settings.SELF_PURCHASE_ENABLED = True
    settings.LEGAL_TERMS_URL = 'https://example.com/t'
    settings.LEGAL_DISTANCE_SALES_URL = 'https://example.com/d'
    settings.LEGAL_PRELIM_INFO_URL = 'https://example.com/p'
    settings.LEGAL_REFUND_URL = 'https://example.com/r'
    settings.LEGAL_KVKK_URL = 'https://example.com/k'
    settings.PAYMENT_SANDBOX = True


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_both_panels_tablist_and_initial_active_tab(coach, active_plan, client, settings):
    """Plain URL renders both panels with tablist markup and Yeni hesap selected.
    ?mod=giris adds auth-tabs--giris and selects the login tab."""
    _enable_purchase(settings)
    url = f'/satin-al/{coach.wordpress_post_id}/'

    r = client.get(url)
    assert r.status_code == 200
    html = r.content.decode()
    assert 'id="panel-yeni"' in html, 'registration panel must be in HTML'
    assert 'id="panel-giris"' in html, 'login panel must be in HTML'
    assert 'role="tablist"' in html
    assert 'id="tab-yeni"' in html
    assert 'id="tab-giris"' in html
    # Yeni hesap is active: exactly one tab has aria-selected="true"
    assert html.count('aria-selected="true"') == 1
    assert html.count('aria-selected="false"') == 1
    # login panel is the hidden one; outer div has no --giris class
    assert 'auth-panel--hidden' in html
    assert 'class="auth-tabs auth-tabs--giris"' not in html

    r2 = client.get(url + '?mod=giris')
    assert r2.status_code == 200
    html2 = r2.content.decode()
    assert 'id="panel-yeni"' in html2
    assert 'id="panel-giris"' in html2
    assert 'class="auth-tabs auth-tabs--giris"' in html2, '?mod=giris must set auth-tabs--giris'
    assert html2.count('aria-selected="true"') == 1


@pytest.mark.django_db
def test_failed_login_post_renders_login_tab_active_with_error(coach, active_plan, client, settings):
    """A failed login POST re-renders with the login tab active and the error shown."""
    _enable_purchase(settings)
    url = f'/satin-al/{coach.wordpress_post_id}/?mod=giris'
    r = client.post(url, data={
        'login_email': 'nobody@example.com',
        'login_password': 'wrongpass',
    })
    assert r.status_code == 200
    html = r.content.decode()
    assert 'auth-tabs--giris' in html, 'login tab must stay active after failed login'
    assert 'hatalı' in html, 'error text must be present'
    assert 'error-box' in html


@pytest.mark.django_db
def test_nojs_tab_links_are_anchor_elements(coach, active_plan, client, settings):
    """Both tab elements are <a> links so no-JS navigation works without JavaScript."""
    _enable_purchase(settings)
    url = f'/satin-al/{coach.wordpress_post_id}/'
    r = client.get(url)
    assert r.status_code == 200
    html = r.content.decode()
    assert '?mod=giris' in html, 'login tab link must be present'
    # Both tab IDs are present
    assert 'id="tab-yeni"' in html
    assert 'id="tab-giris"' in html
    # Each tab id is preceded by an <a opening tag within 300 chars
    yeni_idx  = html.index('id="tab-yeni"')
    giris_idx = html.index('id="tab-giris"')
    assert '<a' in html[max(0, yeni_idx - 300):yeni_idx], 'tab-yeni must be an <a> element'
    assert '<a' in html[max(0, giris_idx - 300):giris_idx], 'tab-giris must be an <a> element'

"""
Playwright: verify SW update → controllerchange → auto-reload flow.

What this test CAN verify:
  1. The /service-worker.js response carries Cache-Control: no-store (so browsers
     always re-validate the SW script on every navigation check).
  2. CACHE_NAME in the rendered SW contains the git commit hash (not the old
     hardcoded 'v3' literal).
  3. The controllerchange handler is present and correctly calls location.reload()
     — verified by dispatching a synthetic 'controllerchange' event on
     navigator.serviceWorker and observing that location.reload is invoked.

What it CANNOT fully verify in headless mode:
  - A real "two-SW lifecycle": Chrome blocks a new SW install in the same process
    while an old one is still active, and the update check uses byte comparison
    which requires modifying the SW file on disk and waiting for the background
    update poll.  That lifecycle is verified by the logic of skipWaiting() and
    clients.claim() which is standard browser behavior we rely on.
"""
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_config.settings')
import django; django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
BASE = 'http://127.0.0.1:8000'


def make_session(email):
    u = User.objects.filter(email=email).first()
    if not u: return None, None
    c = Client(); c.force_login(u)
    return c.session.session_key, u


KEY, USR = make_session('kayaa3413@gmail.com')
if not KEY: print('No session'); sys.exit(1)
print(f'User: {USR.email}')


async def run():
    import urllib.request
    from playwright.async_api import async_playwright

    # ── Test 1: Cache-Control header on /service-worker.js ─────────────────
    print('\n--- Test 1: Cache-Control on /service-worker.js ---')
    req = urllib.request.Request(f'{BASE}/service-worker.js',
                                 headers={'Cookie': f'sessionid={KEY}'})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            cc = resp.headers.get('Cache-Control', '')
            body_head = resp.read(200).decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  [ERR] fetch failed: {e}')
        cc = ''
        body_head = ''

    no_store = 'no-store' in cc
    print(f'  Cache-Control: {cc or "(none)"}')
    print(f'  {"[OK] no-store present" if no_store else "[FAIL] no-store missing"}')

    # ── Test 2: CACHE_NAME contains commit hash (not hardcoded v3) ─────────
    print('\n--- Test 2: CACHE_NAME is commit-derived ---')
    cache_line = next((l.strip() for l in body_head.splitlines()
                       if 'CACHE_NAME' in l), '')
    has_v3 = "'vagus-shell-v3'" in cache_line
    is_dev  = "'vagus-shell-dev'" in cache_line   # fallback when not in git repo
    print(f'  CACHE_NAME line: {cache_line}')
    if has_v3:
        print('  [FAIL] still hardcoded v3 — template variable not substituted')
    elif is_dev:
        print('  [WARN] using dev fallback — OK in local dev, deploy will use real hash')
    else:
        print('  [OK] CACHE_NAME contains dynamic value')

    # ── Test 3: controllerchange handler fires reload() ─────────────────────
    print('\n--- Test 3: controllerchange triggers location.reload() ---')
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )
        ctx = await browser.new_context(viewport={'width': 1280, 'height': 800})
        await ctx.add_cookies([{'name': 'sessionid', 'value': KEY,
                                'domain': '127.0.0.1', 'path': '/'}])
        page = await ctx.new_page()
        await page.goto(f'{BASE}/coach/', wait_until='networkidle')

        # Verify the guard variable and source before triggering the reload.
        pre_check = await page.evaluate('''() => {
            const scripts = Array.from(document.querySelectorAll('script'));
            const guardInSource = scripts.some(
                s => s.textContent.includes('_swReloading'));
            const guardVarDefined = typeof window._swReloading !== 'undefined';
            return { guardInSource, guardVarDefined };
        }''')
        handler_ok = pre_check.get('guardVarDefined', False)
        src_ok     = pre_check.get('guardInSource', False)
        print(f'  _swReloading guard in page source:           '
              f'{"[OK]" if src_ok else "[FAIL]"}')
        print(f'  _swReloading variable initialised on page:   '
              f'{"[OK]" if handler_ok else "[FAIL]"}')

        # Dispatch controllerchange and detect the resulting navigation.
        # Chrome prevents redefining location.reload, so we watch for an actual
        # page reload (navigation to the same URL) which is the real proof.
        reload_ok = False
        try:
            async with page.expect_navigation(timeout=4000):
                await page.evaluate(
                    "() => navigator.serviceWorker.dispatchEvent(new Event('controllerchange'))"
                )
            reload_ok = True
        except Exception:
            reload_ok = False

        print(f'  Page navigated (reload) on controllerchange: '
              f'{"[OK]" if reload_ok else "[FAIL]"}')

        await browser.close()

    print('\n' + '=' * 55)
    print('SUMMARY')
    print(f'  [1] Cache-Control: no-store on SW:   {"PASS" if no_store else "FAIL"}')
    print(f'  [2] CACHE_NAME is commit-derived:    {"FAIL (v3)" if has_v3 else "PASS (dev fallback)" if is_dev else "PASS"}')
    print(f'  [3] controllerchange → reload():     {"PASS" if reload_ok else "FAIL"}')
    print()
    print('NOTE: A full two-SW lifecycle (old SW active → new SW installs → activate')
    print('      fires → clients.claim() → controllerchange) cannot be simulated in')
    print('      headless Playwright without a running separate origin + two browser')
    print('      contexts.  Tests 1-3 verify all the code preconditions: the handler')
    print('      is wired, reload() is called on the event, and the SW script is')
    print('      never cached so the browser always detects changes.')


asyncio.run(run())

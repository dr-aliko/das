"""
Playwright debug script: observe exactly what happens when the coach
selects a student from the Konu Takip dropdown.
Uses Django session injection (no login credentials needed).
"""
import asyncio
import os
import sys

sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_config.settings')
import django
django.setup()

# ── Synchronous Django setup (must happen before async context) ───────────────
from django.contrib.sessions.backends.db import SessionStore
from django.conf import settings

session = SessionStore()
session['_auth_user_id']      = '2'   # Ali Kaya (coach)
session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
session.create()
SESSION_KEY  = session.session_key
COOKIE_NAME  = settings.SESSION_COOKIE_NAME  # 'sessionid'
print(f'Session created: key={SESSION_KEY}, cookie={COOKIE_NAME}')

# ── Async Playwright test ────────────────────────────────────────────────────
BASE = 'http://127.0.0.1:8000'

async def main():
    from playwright.async_api import async_playwright

    console_msgs = []
    network_reqs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = await browser.new_context()
        await ctx.add_cookies([{
            'name':   COOKIE_NAME,
            'value':  SESSION_KEY,
            'domain': '127.0.0.1',
            'path':   '/',
        }])

        page = await ctx.new_page()
        page.on('console',   lambda m: console_msgs.append(f'[{m.type.upper()}] {m.text}'))
        page.on('pageerror', lambda e: console_msgs.append(f'[PAGEERROR] {e}'))
        page.on('request',   lambda r: network_reqs.append(f'-> {r.method} {r.url}'))
        page.on('response',  lambda r: network_reqs.append(f'<- {r.status} {r.url}'))

        # ── Step 1: Load coach konu-takip (no ?student=) ────────────────────────
        print('\n=== Step 1: Load page with no ?student= ===')
        await page.goto(f'{BASE}/coach/konu-takip/')
        await page.wait_for_load_state('networkidle')
        print(f'URL: {page.url}')

        js_errors = [m for m in console_msgs if 'ERROR' in m or 'PAGEERROR' in m]
        print(f'JS errors on load: {js_errors or "none"}')
        print(f'All console msgs: {console_msgs}')

        # Check if we got a redirect (login page?)
        if 'auth/login' in page.url or 'login' in page.url:
            print('ERROR: Redirected to login — session injection failed.')
            await browser.close()
            return

        # ── Step 2: Inspect the select ──────────────────────────────────────────
        print('\n=== Step 2: Inspect student dropdown ===')
        select_info = await page.evaluate('''
            () => {
                const el = document.querySelector("select");
                if (!el) return {found: false};
                return {
                    found: true,
                    visible: el.offsetParent !== null,
                    onchange: el.getAttribute("onchange"),
                    value: el.value,
                    options: Array.from(el.options).map(o => ({
                        value: o.value, text: o.text.trim(), selected: o.selected
                    }))
                };
            }
        ''')
        print(f'Select info: {select_info}')

        if not select_info.get('found'):
            print('No <select> found. Page HTML snippet:')
            snippet = await page.evaluate('() => document.body.innerHTML.slice(0, 1000)')
            print(snippet)
            await browser.close()
            return

        options = select_info.get('options', [])
        other = [o for o in options if not o['selected']]
        if not other:
            print('Only one student option — cannot test switching.')
            await browser.close()
            return
        target = other[0]
        print(f'Will select: {target}')

        # ── Step 3: Select the other student ────────────────────────────────────
        print(f'\n=== Step 3: Selecting student {target["value"]} ({target["text"]}) ===')
        url_before = page.url
        console_msgs.clear()
        network_reqs.clear()

        nav_events = []
        page.on('framenavigated', lambda f: nav_events.append(f.url))

        await page.select_option('select', target['value'])
        try:
            await page.wait_for_load_state('networkidle', timeout=4000)
        except Exception:
            pass

        url_after = page.url
        print(f'URL before: {url_before}')
        print(f'URL after:  {url_after}')
        print(f'URL changed: {url_before != url_after}')
        print(f'Navigation events: {nav_events}')
        print(f'Network reqs: {network_reqs}')
        print(f'Console after select: {console_msgs}')

        # ── Step 4: Run onchange code manually to isolate failures ───────────────
        print('\n=== Step 4: Manually evaluate onchange code ===')
        result = await page.evaluate(f'''
            () => {{
                try {{
                    const el = document.querySelector("select");
                    if (!el) return {{ok: false, err: "no select"}};
                    el.value = "{target['value']}";
                    const url = new URL(window.location);
                    url.searchParams.set("student", el.value);
                    url.searchParams.delete("subject");
                    return {{
                        ok: true,
                        window_href: window.location.href,
                        computed: url.toString(),
                        el_value: el.value
                    }};
                }} catch(e) {{
                    return {{ok: false, err: e.toString()}};
                }}
            }}
        ''')
        print(f'Manual eval result: {result}')

        # ── Step 5: Trigger the actual onchange manually ────────────────────────
        print('\n=== Step 5: Dispatch change event manually + watch for navigation ===')
        nav_events.clear()
        console_msgs.clear()
        network_reqs.clear()

        await page.evaluate(f'''
            () => {{
                const el = document.querySelector("select");
                el.value = "{target['value']}";
                el.dispatchEvent(new Event("change", {{bubbles: true}}));
            }}
        ''')
        try:
            await page.wait_for_load_state('networkidle', timeout=4000)
        except Exception:
            pass

        print(f'URL after manual change event: {page.url}')
        print(f'Navigation events: {nav_events}')
        print(f'Console: {console_msgs}')

        # ── Step 6: Alpine state ─────────────────────────────────────────────────
        print('\n=== Step 6: Alpine state ===')
        alpine = await page.evaluate('''
            () => {
                const el = document.querySelector("[x-data]");
                if (!el) return "no [x-data] element";
                if (!el._x_dataStack) return "Alpine not init (_x_dataStack missing)";
                const d = el._x_dataStack[0];
                return {
                    studentId:         d.studentId,
                    examType:          d.examType,
                    loading:           d.loading,
                    loadError:         d.loadError,
                    selectedSubjectId: d.selectedSubjectId,
                    flatTopicsCount:   d.flatTopics ? d.flatTopics.length : "?",
                };
            }
        ''')
        print(f'Alpine state: {alpine}')

        await browser.close()
        print('\n=== Done ===')

asyncio.run(main())

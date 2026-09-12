"""Minimal Playwright debug: observe student select onchange behavior."""
import asyncio

SESSION_VAL = 'eu9kvckxwe1ac3r8j9ob6p263a9d2aav'
BASE = 'http://127.0.0.1:8000'

async def run():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True)
        ctx = await br.new_context()
        await ctx.add_cookies([{
            'name': 'sessionid', 'value': SESSION_VAL,
            'domain': '127.0.0.1', 'path': '/',
        }])
        page = await ctx.new_page()

        console = []
        page.on('console', lambda m: console.append(f'[{m.type}] {m.text}'))
        page.on('pageerror', lambda e: console.append(f'[ERR] {e}'))

        # Load page
        resp = await page.goto(f'{BASE}/coach/konu-takip/', wait_until='networkidle')
        url1 = page.url
        print(f'Page loaded: {url1}, status={resp.status}')
        print(f'Console on load: {console}')

        # Was we redirected to login?
        if 'login' in url1:
            print('REDIRECT TO LOGIN — session invalid')
            body = await page.content()
            print(body[:500])
            await br.close()
            return

        # Get select info
        info = await page.evaluate('''() => {
            const s = document.querySelector("select");
            if (!s) return {found: false};
            return {
                found: true,
                value: s.value,
                onchange: s.getAttribute("onchange"),
                options: Array.from(s.options).map(o => ({v: o.value, t: o.text.trim(), sel: o.selected}))
            };
        }''')
        print(f'Select info: {info}')

        if not info.get('found'):
            print('NO SELECT FOUND — page body:')
            print((await page.content())[:2000])
            await br.close()
            return

        opts = info['options']
        other = [o for o in opts if not o['sel']]
        if not other:
            print('No other options to select')
            await br.close()
            return

        target_val = other[0]['v']
        print(f'Switching to: {other[0]}')

        # Listen for navigation
        nav = []
        page.on('framenavigated', lambda f: nav.append(f.url) if f == page.main_frame else None)

        console.clear()
        url_before = page.url

        # Programmatically change the select and fire onchange
        changed = await page.evaluate(f'''() => {{
            const s = document.querySelector("select");
            s.value = "{target_val}";
            // Fire the change event as the browser would
            s.dispatchEvent(new Event("change", {{bubbles: true}}));
            return {{fired: true, newValue: s.value}};
        }}''')
        print(f'Change event dispatched: {changed}')

        # Wait a bit for potential navigation
        await asyncio.sleep(2)

        url_after = page.url
        print(f'URL before: {url_before}')
        print(f'URL after:  {url_after}')
        print(f'URL changed: {url_before != url_after}')
        print(f'Nav events: {nav}')
        print(f'Console after: {console}')

        # Also check: what does window.location.href assignment DO?
        href_test = await page.evaluate('''() => {
            try {
                const url = new URL(window.location);
                url.searchParams.set("student", "4");
                url.searchParams.delete("subject");
                return {
                    ok: true,
                    computed: url.toString(),
                    current: window.location.href
                };
            } catch(e) {
                return {ok: false, err: String(e)};
            }
        }''')
        print(f'URL computation test: {href_test}')

        # Alpine state
        alpine = await page.evaluate('''() => {
            const el = document.querySelector("[x-data]");
            if (!el) return "no x-data";
            if (!el._x_dataStack) return "Alpine not initialized";
            const d = el._x_dataStack[0];
            return {studentId: d.studentId, examType: d.examType, loading: d.loading};
        }''')
        print(f'Alpine state: {alpine}')

        await br.close()
        print('DONE')

asyncio.run(run())

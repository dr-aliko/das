"""Probe Alpine v3 data accessor — find correct way to read/write component data."""
import asyncio, os, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_config.settings')
import django; django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
User = get_user_model()
BASE = 'http://127.0.0.1:8000'

u = User.objects.filter(email='kayaa3413@gmail.com').first()
c = Client(); c.force_login(u)
KEY = c.session.session_key

async def run():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = await browser.new_context(viewport={'width':1400,'height':900})
        await ctx.add_cookies([{'name':'sessionid','value':KEY,'domain':'127.0.0.1','path':'/'}])
        page = await ctx.new_page()

        async def stub(route, req):
            await route.fulfill(content_type='application/json',
                                body=json.dumps({'dersler':[],'listeler':[],'videolar':[],'gorevler':[]}))
        await page.route('**/api/**', stub)

        await page.goto(f'{BASE}/coach/tasks/', wait_until='networkidle')
        await page.wait_for_timeout(1500)

        info = await page.evaluate('''() => {
            const roots = Array.from(document.querySelectorAll("[x-data]"));
            const hasAlpine = typeof window.Alpine !== "undefined";
            return {
                alpineInWindow: hasAlpine,
                alpineVersion: hasAlpine ? (window.Alpine.version || "?") : "none",
                roots: roots.map(el => {
                    const attr = el.getAttribute("x-data") || "";
                    let keys = [];
                    let method = "none";
                    // Try Alpine v3: window.Alpine.$data(el)
                    if (hasAlpine && window.Alpine.$data) {
                        try {
                            const d = window.Alpine.$data(el);
                            keys = Object.keys(d).slice(0,10);
                            method = "Alpine.$data";
                        } catch(e) {}
                    }
                    // Try _x_dataStack
                    if (!keys.length && el._x_dataStack) {
                        try {
                            keys = Object.keys(el._x_dataStack[0] || {}).slice(0,10);
                            method = "_x_dataStack[0]";
                        } catch(e) {}
                    }
                    return {
                        xdata: attr.slice(0,40),
                        method,
                        keys,
                    };
                })
            };
        }''')
        print(json.dumps(info, indent=2, ensure_ascii=False))
        await browser.close()

asyncio.run(run())

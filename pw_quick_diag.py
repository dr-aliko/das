"""Quick diagnostic — find exactly where pw_verify_hafta.py hangs."""
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stdout.flush()

print('Step 1: stdout works', flush=True)

sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_config.settings')
import django; django.setup()
print('Step 2: Django ready', flush=True)

from django.test import Client
from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.filter(email='kayaa3413@gmail.com').first()
c = Client(); c.force_login(u)
KEY = c.session.session_key
print(f'Step 3: session key = {KEY[:8]}...', flush=True)

async def run():
    from playwright.async_api import async_playwright
    print('Step 4: importing async_playwright done', flush=True)
    async with async_playwright() as p:
        print('Step 5: playwright context open', flush=True)
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']
        )
        print('Step 6: browser launched', flush=True)
        ctx = await browser.new_context(viewport={'width':1400,'height':900})
        await ctx.add_cookies([{'name':'sessionid','value':KEY,'domain':'127.0.0.1','path':'/'}])
        page = await ctx.new_page()
        print('Step 7: page created, navigating...', flush=True)
        try:
            await page.goto('http://127.0.0.1:8000/coach/tasks/', wait_until='domcontentloaded', timeout=20000)
            print('Step 8: page loaded (domcontentloaded)', flush=True)
        except Exception as e:
            print(f'Step 8 FAIL: {e}', flush=True)
        await browser.close()
        print('Step 9: done', flush=True)

asyncio.run(run())

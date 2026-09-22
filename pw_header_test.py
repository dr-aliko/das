"""Playwright: verify collapsed/expanded sidebar header interaction."""
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_config.settings')
import django; django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
BASE  = 'http://127.0.0.1:8000'
SHOTS = 'C:/tmp/header_shots'
os.makedirs(SHOTS, exist_ok=True)

def make_session(email):
    u = User.objects.filter(email=email).first()
    if not u: return None, None
    c = Client(); c.force_login(u)
    return c.session.session_key, u

KEY, USR = make_session('kayaa3413@gmail.com')
if not KEY: print('No session'); sys.exit(1)
print(f'User: {USR.email}')

HEADER_JS = '''() => {
    const header = document.querySelector(".das-brand-header");
    const logo   = document.querySelector(".das-brand-logo-link");
    const toggle = document.querySelector(".das-sidebar-toggle");
    const collapsed = document.documentElement.classList.contains("sidebar-collapsed");
    if (!header || !logo) return { error: "elements missing" };
    const hr = header.getBoundingClientRect();
    const lr = logo.getBoundingClientRect();
    const cs = window.getComputedStyle(logo);
    const toggleVisible = toggle
        ? window.getComputedStyle(toggle).display !== "none"
        : false;
    const toggleRect = toggle ? toggle.getBoundingClientRect() : null;
    const overlap = toggle && toggleVisible
        ? !(lr.right <= toggleRect.left || toggleRect.right <= lr.left ||
            lr.bottom <= toggleRect.top || toggleRect.bottom <= lr.top)
        : false;
    return {
        collapsed,
        header:       { w: hr.width, h: hr.height },
        logo:         { t: lr.top, l: lr.left, w: lr.width, h: lr.height, cursor: cs.cursor },
        toggleVisible,
        toggleRect,
        overlap,
    };
}'''


def report(label, r):
    print(f'\n--- {label} ---')
    if 'error' in r:
        print(f'  [ERR] {r["error"]}'); return
    print(f'  collapsed={r["collapsed"]}')
    print(f'  header:   {r["header"]["w"]:.0f}x{r["header"]["h"]:.0f}px')
    print(f'  logo:     top={r["logo"]["t"]:.0f} left={r["logo"]["l"]:.0f} '
          f'{r["logo"]["w"]:.0f}x{r["logo"]["h"]:.0f}px  cursor={r["logo"]["cursor"]}')
    print(f'  toggle visible: {r["toggleVisible"]}', end='')
    if r["toggleVisible"] and r["toggleRect"]:
        tr = r["toggleRect"]
        print(f'  at top={tr["top"]:.0f} left={tr["left"]:.0f} '
              f'{tr["width"]:.0f}x{tr["height"]:.0f}px', end='')
    print()
    if r["overlap"]:
        print(f'  [OVERLAP] logo and toggle overlap!')
    else:
        print(f'  [OK] no logo/toggle overlap')


async def run():
    from playwright.async_api import async_playwright
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

        # ── 1. Start EXPANDED ────────────────────────────────────────────
        await page.evaluate('''() => {
            document.documentElement.classList.remove("sidebar-collapsed");
            localStorage.removeItem("das-sidebar-collapsed");
        }''')
        await page.wait_for_timeout(350)

        r_exp = await page.evaluate(HEADER_JS)
        report('EXPANDED state (initial)', r_exp)
        await page.screenshot(path=f'{SHOTS}/01_expanded.png', full_page=False)

        # Cropped header
        sb = await page.query_selector('aside.das-sidebar')
        if sb:
            box = await sb.bounding_box()
            await page.screenshot(path=f'{SHOTS}/02_expanded_header_crop.png',
                                  clip={'x': box['x'], 'y': box['y'],
                                        'width': box['width'], 'height': 60})

        # ── 2. Click the CHEVRON to collapse ────────────────────────────
        toggle_btn = await page.query_selector('.das-sidebar-toggle')
        if toggle_btn:
            await toggle_btn.click()
            await page.wait_for_timeout(400)
            r_after_chevron = await page.evaluate(HEADER_JS)
            report('After clicking CHEVRON (should now be collapsed)', r_after_chevron)
            await page.screenshot(path=f'{SHOTS}/03_after_chevron_click.png', full_page=False)
            sb2 = await page.query_selector('aside.das-sidebar')
            if sb2:
                box2 = await sb2.bounding_box()
                await page.screenshot(path=f'{SHOTS}/04_collapsed_header_crop.png',
                                      clip={'x': box2['x'], 'y': box2['y'],
                                            'width': box2['width'], 'height': 80})
        else:
            print('\n[WARN] .das-sidebar-toggle not found')

        # ── 3. Click the LOGO to expand ─────────────────────────────────
        logo_link = await page.query_selector('.das-brand-logo-link')
        if logo_link:
            await logo_link.click()
            await page.wait_for_timeout(400)
            r_after_logo = await page.evaluate(HEADER_JS)
            report('After clicking LOGO (should now be expanded)', r_after_logo)
            await page.screenshot(path=f'{SHOTS}/05_after_logo_click.png', full_page=False)
        else:
            print('\n[WARN] .das-brand-logo-link not found')

        await browser.close()

    print('\n' + '='*55)
    print('SCREENSHOTS:', SHOTS)
    ok = True
    if 'collapsed' in r_exp:
        if r_exp['collapsed']:
            print('[FAIL] expanded state still shows collapsed=True'); ok = False
        if r_exp['toggleVisible']:
            print('[OK]   chevron visible in expanded state')
        else:
            print('[FAIL] chevron NOT visible in expanded state'); ok = False
        if not r_exp['overlap']:
            print('[OK]   no overlap in expanded state')

    if 'collapsed' in r_after_chevron:
        if r_after_chevron['collapsed']:
            print('[OK]   chevron click correctly collapsed the sidebar')
        else:
            print('[FAIL] chevron click did NOT collapse'); ok = False
        if not r_after_chevron['toggleVisible']:
            print('[OK]   chevron hidden in collapsed state')
        else:
            print('[FAIL] chevron still visible in collapsed state'); ok = False
        if not r_after_chevron['overlap']:
            print('[OK]   no overlap in collapsed state')

    if 'collapsed' in r_after_logo:
        if not r_after_logo['collapsed']:
            print('[OK]   logo click correctly expanded the sidebar')
        else:
            print('[FAIL] logo click did NOT expand'); ok = False

    print('RESULT:', '[OK] all checks passed' if ok else '[FAIL] see above')


asyncio.run(run())

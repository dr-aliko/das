"""Playwright: verify nav icon centering in collapsed sidebar."""
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_config.settings')
import django; django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
BASE  = 'http://127.0.0.1:8000'
SHOTS = 'C:/tmp/navicon_shots'
os.makedirs(SHOTS, exist_ok=True)

def make_session(email):
    u = User.objects.filter(email=email).first()
    if not u: return None, None
    c = Client(); c.force_login(u)
    return c.session.session_key, u

KEY, USR = make_session('kayaa3413@gmail.com')
if not KEY: print('No session'); sys.exit(1)
print(f'User: {USR.email}')

MEASURE_JS = '''() => {
    const link = document.querySelector(".das-nav-link");
    if (!link) return { error: "no .das-nav-link found" };
    const icon = link.querySelector("svg");
    if (!icon) return { error: "no svg inside nav-link" };
    const lr = link.getBoundingClientRect();
    const ir = icon.getBoundingClientRect();
    const ls = window.getComputedStyle(link);
    // Icon center relative to link inner area
    const linkCenterX = lr.left + lr.width / 2;
    const iconCenterX = ir.left + ir.width / 2;
    const linkCenterY = lr.top + lr.height / 2;
    const iconCenterY = ir.top + ir.height / 2;
    return {
        link:  { l: lr.left, t: lr.top, w: lr.width, h: lr.height,
                 justifyContent: ls.justifyContent, gap: ls.gap },
        icon:  { l: ir.left, t: ir.top, w: ir.width, h: ir.height },
        offsetX: iconCenterX - linkCenterX,
        offsetY: iconCenterY - linkCenterY,
    };
}'''


def report(label, r):
    print(f'\n--- {label} ---')
    if 'error' in r:
        print(f'  [ERR] {r["error"]}'); return
    ox, oy = r['offsetX'], r['offsetY']
    print(f'  link: {r["link"]["w"]:.0f}x{r["link"]["h"]:.0f}px  '
          f'justifyContent={r["link"]["justifyContent"]}  gap={r["link"]["gap"]}')
    print(f'  icon: {r["icon"]["w"]:.0f}x{r["icon"]["h"]:.0f}px  '
          f'left={r["icon"]["l"]:.1f}  top={r["icon"]["t"]:.1f}')
    print(f'  icon center offset from link center: x={ox:+.1f}px  y={oy:+.1f}px')
    centered = abs(ox) <= 2 and abs(oy) <= 2
    print(f'  {"[OK] icon is centered (within 2px)" if centered else f"[FAIL] icon offset too large"}')


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

        # ── EXPANDED: baseline ───────────────────────────────────────────
        await page.evaluate('''() => {
            document.documentElement.classList.remove("sidebar-collapsed");
            localStorage.removeItem("das-sidebar-collapsed");
        }''')
        await page.wait_for_timeout(350)
        r_exp = await page.evaluate(MEASURE_JS)
        report('EXPANDED first nav-link', r_exp)

        # Crop: first nav-link in expanded sidebar
        link_exp = await page.query_selector('.das-nav-link')
        if link_exp:
            box = await link_exp.bounding_box()
            await page.screenshot(path=f'{SHOTS}/01_expanded_navlink.png',
                                  clip={'x': 0, 'y': box['y'] - 4,
                                        'width': 250, 'height': box['height'] + 8})

        # ── COLLAPSED ────────────────────────────────────────────────────
        await page.evaluate('''() => {
            document.documentElement.classList.add("sidebar-collapsed");
            localStorage.setItem("das-sidebar-collapsed", "1");
        }''')
        await page.wait_for_timeout(400)
        r_col = await page.evaluate(MEASURE_JS)
        report('COLLAPSED first nav-link', r_col)

        # Crop: first nav-link in collapsed sidebar (full sidebar width, tight crop)
        link_col = await page.query_selector('.das-nav-link')
        if link_col:
            box2 = await link_col.bounding_box()
            await page.screenshot(path=f'{SHOTS}/02_collapsed_navlink.png',
                                  clip={'x': 0, 'y': box2['y'] - 4,
                                        'width': 68, 'height': box2['height'] + 8})

        # Full sidebar screenshot collapsed for context
        sb = await page.query_selector('aside.das-sidebar')
        if sb:
            sbox = await sb.bounding_box()
            await page.screenshot(path=f'{SHOTS}/03_collapsed_sidebar_full.png',
                                  clip={'x': sbox['x'], 'y': sbox['y'],
                                        'width': sbox['width'], 'height': 300})

        await browser.close()

    print('\n' + '='*50)
    print('SCREENSHOTS:', SHOTS)
    if 'offsetX' in r_exp:
        print(f'EXPANDED  icon offset: x={r_exp["offsetX"]:+.1f}  y={r_exp["offsetY"]:+.1f}  '
              f'(left-aligned, x offset expected)')
    if 'offsetX' in r_col:
        ox, oy = r_col['offsetX'], r_col['offsetY']
        ok = abs(ox) <= 2 and abs(oy) <= 2
        print(f'COLLAPSED icon offset: x={ox:+.1f}  y={oy:+.1f}  '
              f'{"[OK] centered" if ok else "[FAIL] not centered"}')


asyncio.run(run())

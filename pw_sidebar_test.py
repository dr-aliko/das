"""Real Playwright sidebar layout verification."""
import asyncio, os, sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_config.settings')

import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
BASE = 'http://127.0.0.1:8000'
SHOTS = 'C:/tmp/sidebar_shots'
os.makedirs(SHOTS, exist_ok=True)

# Get session synchronously BEFORE entering async context
def make_session(email):
    user = User.objects.filter(email=email).first()
    if not user:
        user = User.objects.filter(is_active=True).order_by('-date_joined').first()
    if not user:
        return None, None
    c = Client()
    c.force_login(user)
    return c.session.session_key, user

SESSION_KEY, TEST_USER = make_session('kayaa3413@gmail.com')
if not SESSION_KEY:
    print('No users found -- aborting')
    sys.exit(1)

IS_STUDENT = getattr(TEST_USER, 'is_student', False)
ROLE = 'student' if IS_STUDENT else 'coach'
HOME  = f'{BASE}/student/' if IS_STUDENT else f'{BASE}/coach/'
TASKS = f'{BASE}/student/tasks/' if IS_STUDENT else f'{BASE}/coach/tasks/'

print(f'User: {TEST_USER.email}, role={ROLE}, session={SESSION_KEY[:12]}...')


async def measure(page, label):
    r = await page.evaluate('''() => {
        const sidebar = document.querySelector("aside.das-sidebar");
        const main    = document.getElementById("das-main");
        if (!sidebar) {
            const allAsides = Array.from(document.querySelectorAll("aside")).map(a => a.className.slice(0,60));
            return { error: "aside.das-sidebar not found", allAsides };
        }
        if (!main) {
            const allMains = Array.from(document.querySelectorAll("main")).map(m => ({id:m.id, cls:m.className.slice(0,60)}));
            return { error: "#das-main not found", allMains };
        }
        const ss  = window.getComputedStyle(sidebar);
        const ms  = window.getComputedStyle(main);
        const sbr = sidebar.getBoundingClientRect();
        const mr  = main.getBoundingClientRect();
        return {
            htmlClasses: document.documentElement.className,
            sidebar: { display:ss.display, position:ss.position,
                       width:ss.width, rectRight: sbr.right },
            main: {
                marginLeft:  ms.marginLeft,
                paddingLeft: ms.paddingLeft,
                rectLeft:    mr.left,
                classList:   Array.from(main.classList).join(" "),
            },
            gap: mr.left - sbr.right,
        };
    }''')
    print(f'\n--- {label} ---')
    if 'error' in r:
        print(f'  [ERR] {r["error"]}')
        print(f'  allAsides: {r.get("allAsides", r.get("allMains", ""))}')
        return r
    overlap = r['gap'] < 0
    print(f'  html.classes   = "{r["htmlClasses"]}"')
    print(f'  sidebar.display= {r["sidebar"]["display"]}, position={r["sidebar"]["position"]}, '
          f'width={r["sidebar"]["width"]}, rectRight={r["sidebar"]["rectRight"]:.0f}px')
    print(f'  main.marginLeft= {r["main"]["marginLeft"]}, paddingLeft={r["main"]["paddingLeft"]}')
    print(f'  main.rectLeft  = {r["main"]["rectLeft"]:.0f}px')
    print(f'  main.classList = "{r["main"]["classList"][:80]}"')
    print(f'  gap (main.left - sidebar.right) = {r["gap"]:.1f}px  '
          f'{"[OVERLAP] content behind sidebar!" if overlap else "[OK] content clear of sidebar"}')
    return r


async def run():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )

        async def auth_ctx(w=1280, h=800):
            ctx = await browser.new_context(viewport={'width': w, 'height': h})
            await ctx.add_cookies([{
                'name': 'sessionid', 'value': SESSION_KEY,
                'domain': '127.0.0.1', 'path': '/',
            }])
            return ctx

        # Test 1: Expanded sidebar, home page, 1280px
        ctx = await auth_ctx(1280)
        page = await ctx.new_page()
        resp = await page.goto(HOME, wait_until='networkidle')
        final_url = page.url
        print(f'\nLoaded: {final_url}  status={resp.status}')
        if 'login' in final_url:
            print('[WARN] Redirected to login -- session invalid, exiting')
            await browser.close(); return

        await page.evaluate('''() => {
            document.documentElement.classList.remove("sidebar-collapsed");
            localStorage.removeItem("das-sidebar-collapsed");
        }''')
        await page.wait_for_timeout(350)
        await page.screenshot(path=f'{SHOTS}/01_expanded_1280.png')
        m_exp = await measure(page, 'EXPANDED sidebar @ 1280px')

        # Test 2: Collapsed sidebar, same page
        await page.evaluate('''() => {
            document.documentElement.classList.add("sidebar-collapsed");
            localStorage.setItem("das-sidebar-collapsed", "1");
        }''')
        await page.wait_for_timeout(400)
        await page.screenshot(path=f'{SHOTS}/02_collapsed_1280.png')
        m_col = await measure(page, 'COLLAPSED sidebar @ 1280px')

        # Test 3: Navigate to tasks -- verify collapse persists
        await page.goto(TASKS, wait_until='networkidle')
        await page.wait_for_timeout(200)
        still_collapsed = await page.evaluate(
            "() => document.documentElement.classList.contains('sidebar-collapsed')"
        )
        print(f'\n--- POST-NAVIGATION state ---')
        print(f'  sidebar-collapsed class present after navigation: {still_collapsed}  '
              f'{"[OK]" if still_collapsed else "[WARN] LOST -- localStorage restore failed"}')
        await page.screenshot(path=f'{SHOTS}/03_after_nav_tasks.png')
        await measure(page, f'{ROLE.upper()} TASKS PAGE post-navigation')

        # Test 4: Mobile (390px) -- sidebar must be hidden
        await ctx.close()
        ctx_m = await auth_ctx(390, 844)
        page_m = await ctx_m.new_page()
        await page_m.goto(HOME, wait_until='networkidle')
        mob = await page_m.evaluate('''() => {
            const s = document.querySelector("aside.das-sidebar");
            if (!s) return {found: false};
            const cs = window.getComputedStyle(s);
            return {found: true, display: cs.display, width: cs.width};
        }''')
        print(f'\n--- MOBILE @ 390px ---')
        print(f'  sidebar: {mob}  '
              f'{"[OK] hidden on mobile" if mob.get("display") == "none" else "[WARN] visible -- should be hidden!"}')
        await page_m.screenshot(path=f'{SHOTS}/04_mobile_390.png')
        await ctx_m.close()

        await browser.close()

    # Final verdict
    print('\n' + '='*60)
    print('SCREENSHOTS:', SHOTS)
    if 'error' not in m_exp:
        eg = m_exp['gap']
        print(f'EXPANDED:  sidebar.right={m_exp["sidebar"]["rectRight"]:.0f}px, '
              f'main.left={m_exp["main"]["rectLeft"]:.0f}px, gap={eg:.0f}px '
              f'{"[OK]" if eg >= -1 else "[OVERLAP]"}')
    if 'error' not in m_col:
        cg = m_col['gap']
        print(f'COLLAPSED: sidebar.right={m_col["sidebar"]["rectRight"]:.0f}px, '
              f'main.left={m_col["main"]["rectLeft"]:.0f}px, gap={cg:.0f}px '
              f'{"[OK]" if cg >= -1 else "[OVERLAP]"}')


asyncio.run(run())

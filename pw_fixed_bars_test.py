"""Playwright verification: fixed bottom bars are offset past the sidebar."""
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core_config.settings')

import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
BASE  = 'http://127.0.0.1:8000'
SHOTS = 'C:/tmp/bar_shots'
os.makedirs(SHOTS, exist_ok=True)

def make_session(email):
    user = User.objects.filter(email=email).first()
    if not user:
        return None, None
    c = Client()
    c.force_login(user)
    return c.session.session_key, user

# Use coach account for coach-page tests
COACH_KEY, COACH_USER = make_session('kayaa3413@gmail.com')
# Use a student account for student-page tests
STUDENT_KEY, STUDENT_USER = make_session('a@gmail.com')

if not COACH_KEY:
    print('No coach session -- aborting')
    sys.exit(1)

print(f'Coach:   {COACH_USER.email}, session={COACH_KEY[:12]}...')
if STUDENT_USER:
    print(f'Student: {STUDENT_USER.email}, session={STUDENT_KEY[:12]}...')
else:
    print('[WARN] No student session -- exam-create test will be skipped')

# Resolve placement attempt before entering async context
PLACEMENT_ATTEMPT_ID = None
if STUDENT_USER:
    from exams_app.models import StudentExamAttempt
    _att = (StudentExamAttempt.objects.filter(student=STUDENT_USER, is_completed=False)
            .order_by('-id').first()
            or StudentExamAttempt.objects.filter(student=STUDENT_USER).order_by('-id').first())
    PLACEMENT_ATTEMPT_ID = _att.id if _att else None
    print(f'Placement attempt id: {PLACEMENT_ATTEMPT_ID}')


MEASURE_FIXED = '''(selector) => {
    const bar     = document.querySelector(selector);
    const sidebar = document.querySelector("aside.das-sidebar");
    if (!bar)     return { error: "bar not found: " + selector };
    if (!sidebar) return { error: "sidebar not found" };
    const bs  = window.getComputedStyle(bar);
    const ss  = window.getComputedStyle(sidebar);
    const br  = bar.getBoundingClientRect();
    const sbr = sidebar.getBoundingClientRect();
    return {
        bar:     { left: bs.left, rectLeft: br.left },
        sidebar: { display: ss.display, width: ss.width, rectRight: sbr.right },
        overlap: br.left < sbr.right,
        gap:     br.left - sbr.right,
    };
}'''


def report(label, r):
    print(f'\n--- {label} ---')
    if 'error' in r:
        print(f'  [ERR] {r["error"]}')
        return
    status = '[OVERLAP] bar behind sidebar!' if r['overlap'] else '[OK] bar clear of sidebar'
    print(f'  sidebar: width={r["sidebar"]["width"]}, rectRight={r["sidebar"]["rectRight"]:.0f}px')
    print(f'  bar:     left={r["bar"]["left"]}, rectLeft={r["bar"]["rectLeft"]:.0f}px')
    print(f'  gap = {r["gap"]:.1f}px  {status}')


async def run():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )

        async def auth_ctx(session_key, w=1280, h=800):
            ctx = await browser.new_context(viewport={'width': w, 'height': h})
            await ctx.add_cookies([{
                'name': 'sessionid', 'value': session_key,
                'domain': '127.0.0.1', 'path': '/',
            }])
            return ctx

        async def force_expanded(page):
            await page.evaluate('''() => {
                document.documentElement.classList.remove("sidebar-collapsed");
                localStorage.removeItem("das-sidebar-collapsed");
            }''')
            await page.wait_for_timeout(300)

        results = {}

        # ==============================================================
        # Test 1: Exam-create page -- .das-create-footer (student only)
        # ==============================================================
        if STUDENT_KEY:
            ctx = await auth_ctx(STUDENT_KEY, 1280)
            page = await ctx.new_page()
            resp = await page.goto(f'{BASE}/student/exam/new/v2/', wait_until='networkidle')
            print(f'\nLoaded exam-create: {page.url}  status={resp.status}')

            if 'login' not in page.url and 'exam/new/v2' in page.url:
                await force_expanded(page)
                r = await page.evaluate(MEASURE_FIXED, '.das-create-footer')
                report('EXAM CREATE -- .das-create-footer EXPANDED @ 1280px', r)
                results['exam_create_exp'] = r
                await page.screenshot(path=f'{SHOTS}/01_exam_create_expanded.png', full_page=False)

                # Collapsed
                await page.evaluate('''() => {
                    document.documentElement.classList.add("sidebar-collapsed");
                    localStorage.setItem("das-sidebar-collapsed", "1");
                }''')
                await page.wait_for_timeout(350)
                r2 = await page.evaluate(MEASURE_FIXED, '.das-create-footer')
                report('EXAM CREATE -- .das-create-footer COLLAPSED @ 1280px', r2)
                results['exam_create_col'] = r2
                await page.screenshot(path=f'{SHOTS}/02_exam_create_collapsed.png', full_page=False)
            else:
                print(f'  [skip] redirected to {page.url}')
            await ctx.close()

        # ==============================================================
        # Test 2: Student home -- sidebar + main gap (core layout check)
        # ==============================================================
        if STUDENT_KEY:
            ctx2 = await auth_ctx(STUDENT_KEY, 1280)
            page2 = await ctx2.new_page()
            await page2.goto(f'{BASE}/student/', wait_until='networkidle')
            await force_expanded(page2)
            r_home = await page2.evaluate('''() => {
                const sidebar = document.querySelector("aside.das-sidebar");
                const main    = document.getElementById("das-main");
                if (!sidebar || !main) return { error: "elements missing" };
                const sbr = sidebar.getBoundingClientRect();
                const mr  = main.getBoundingClientRect();
                const ms  = window.getComputedStyle(main);
                const ss  = window.getComputedStyle(sidebar);
                return {
                    sidebar: { width: ss.width, rectRight: sbr.right },
                    main: { marginLeft: ms.marginLeft, rectLeft: mr.left },
                    gap: mr.left - sbr.right,
                };
            }''')
            print(f'\n--- STUDENT HOME -- sidebar/main gap EXPANDED @ 1280px ---')
            if 'error' in r_home:
                print(f'  [ERR] {r_home["error"]}')
            else:
                results['home_gap'] = r_home
                status = '[OK] no overlap' if r_home['gap'] >= -1 else '[OVERLAP]'
                print(f'  sidebar.width={r_home["sidebar"]["width"]}, rectRight={r_home["sidebar"]["rectRight"]:.0f}px')
                print(f'  main.marginLeft={r_home["main"]["marginLeft"]}, rectLeft={r_home["main"]["rectLeft"]:.0f}px')
                print(f'  gap = {r_home["gap"]:.1f}px  {status}')
            await page2.screenshot(path=f'{SHOTS}/03_student_home_expanded.png', full_page=False)
            await ctx2.close()

        # ==============================================================
        # Test 3: Placement take page -- already-fixed bar
        # ==============================================================
        if STUDENT_KEY and PLACEMENT_ATTEMPT_ID:
            if True:
                ctx3 = await auth_ctx(STUDENT_KEY, 1280)
                page3 = await ctx3.new_page()
                take_url = f'{BASE}/student/seviye-tespiti/{PLACEMENT_ATTEMPT_ID}/al/'
                resp3 = await page3.goto(take_url, wait_until='networkidle')
                print(f'\nLoaded placement-take: {page3.url}  status={resp3.status}')
                if 'al/' in page3.url:
                    await force_expanded(page3)
                    r3 = await page3.evaluate(MEASURE_FIXED, '.das-fixed-sidebar-offset')
                    report('PLACEMENT TAKE -- fixed bar EXPANDED @ 1280px', r3)
                    results['placement'] = r3
                    await page3.screenshot(path=f'{SHOTS}/04_placement_take_expanded.png', full_page=False)
                await ctx3.close()
            else:
                print('\n[skip] No placement attempt found for this student')

        # ==============================================================
        # Test 4: Coach home -- sidebar/main gap
        # ==============================================================
        ctx4 = await auth_ctx(COACH_KEY, 1280)
        page4 = await ctx4.new_page()
        await page4.goto(f'{BASE}/coach/', wait_until='networkidle')
        await force_expanded(page4)
        r_coach = await page4.evaluate('''() => {
            const sidebar = document.querySelector("aside.das-sidebar");
            const main    = document.getElementById("das-main");
            if (!sidebar || !main) return { error: "elements missing" };
            const sbr = sidebar.getBoundingClientRect();
            const mr  = main.getBoundingClientRect();
            const ss  = window.getComputedStyle(sidebar);
            return {
                sidebar: { width: ss.width, rectRight: sbr.right },
                main: { rectLeft: mr.left },
                gap: mr.left - sbr.right,
            };
        }''')
        print(f'\n--- COACH HOME -- sidebar/main gap EXPANDED @ 1280px ---')
        if 'error' in r_coach:
            print(f'  [ERR] {r_coach["error"]}')
        else:
            results['coach_gap'] = r_coach
            status = '[OK] no overlap' if r_coach['gap'] >= -1 else '[OVERLAP]'
            print(f'  sidebar.width={r_coach["sidebar"]["width"]}, rectRight={r_coach["sidebar"]["rectRight"]:.0f}px')
            print(f'  main.rectLeft={r_coach["main"]["rectLeft"]:.0f}px, gap={r_coach["gap"]:.1f}px  {status}')
        await page4.screenshot(path=f'{SHOTS}/05_coach_home_expanded.png', full_page=False)
        await ctx4.close()

        await browser.close()

    # ── Summary ──────────────────────────────────────────────────────────
    print('\n' + '='*60)
    print('SCREENSHOTS saved to:', SHOTS)
    print()
    if 'exam_create_exp' in results and 'error' not in results['exam_create_exp']:
        r = results['exam_create_exp']
        print(f'EXAM-CREATE EXPANDED:  bar.left={r["bar"]["rectLeft"]:.0f}px, '
              f'sidebar.right={r["sidebar"]["rectRight"]:.0f}px, '
              f'gap={r["gap"]:.0f}px  {"[OK]" if not r["overlap"] else "[OVERLAP]"}')
    if 'exam_create_col' in results and 'error' not in results['exam_create_col']:
        r = results['exam_create_col']
        print(f'EXAM-CREATE COLLAPSED: bar.left={r["bar"]["rectLeft"]:.0f}px, '
              f'sidebar.right={r["sidebar"]["rectRight"]:.0f}px, '
              f'gap={r["gap"]:.0f}px  {"[OK]" if not r["overlap"] else "[OVERLAP]"}')
    if 'home_gap' in results:
        r = results['home_gap']
        print(f'STUDENT HOME GAP:      main.left={r["main"]["rectLeft"]:.0f}px, '
              f'sidebar.right={r["sidebar"]["rectRight"]:.0f}px, '
              f'gap={r["gap"]:.0f}px  {"[OK]" if r["gap"] >= -1 else "[OVERLAP]"}')
    if 'coach_gap' in results:
        r = results['coach_gap']
        print(f'COACH HOME GAP:        main.left={r["main"]["rectLeft"]:.0f}px, '
              f'sidebar.right={r["sidebar"]["rectRight"]:.0f}px, '
              f'gap={r["gap"]:.0f}px  {"[OK]" if r["gap"] >= -1 else "[OVERLAP]"}')
    if 'placement' in results and 'error' not in results['placement']:
        r = results['placement']
        print(f'PLACEMENT TAKE:        bar.left={r["bar"]["rectLeft"]:.0f}px, '
              f'sidebar.right={r["sidebar"]["rectRight"]:.0f}px, '
              f'gap={r["gap"]:.0f}px  {"[OK]" if not r["overlap"] else "[OVERLAP]"}')


asyncio.run(run())

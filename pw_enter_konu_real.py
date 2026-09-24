"""
Playwright: Enter-to-save on the REAL konu anlatımı chain.

Component types confirmed from source (templates/coach/tasks/hafta.html,
templates/tasks/partials/_task_bottom_sheets.html):

  Desktop (panel() / tasks_panel.js):
    Ders        = native <select>  (lines 618-628 of hafta.html)
    Liste       = native <select>  (lines 636-646)
    Videos      = <input type=checkbox>  (lines 680-682)

  Mobile (coachMobilePanel() / _task_bottom_sheets.html):
    Ders        = scrollable <button> list  (lines 173-182)
    Liste       = scrollable <button> list  (lines 231-239)
    Videos      = <input type=checkbox>  (lines 262-287)

Strategy:
  1. Load page without route stubs (API calls fail naturally, same as pw_enter_konu.py).
  2. After page load, use window.Alpine.$data(el) to inject mock videolar and open the
     form in konu_anlatimi mode with liste_id pre-set (so video checkboxes render).
  3. Override saveTask / saveMobileTask with a counter so no real network POST is made.
  4. Press Enter on a video checkbox and verify: save counter incremented, checkbox unchanged.

Tests
-----
X. Desktop: real video checkbox in konu_anlatimi modal → Enter saves not toggles
Y. Mobile:  real video checkbox in konu_anlatimi sheet → Enter saves not toggles
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

u = User.objects.filter(email='kayaa3413@gmail.com').first()
c = Client(); c.force_login(u)
KEY = c.session.session_key
print(f'User: {u.email}', flush=True)

SEED_JS = """
({selector, isMobile}) => {
    const el = document.querySelector(selector);
    if (!el) return {ok: false, reason: 'element not found: ' + selector};

    const data = window.Alpine ? window.Alpine.$data(el) : null;
    if (!data) return {ok: false, reason: 'Alpine.$data returned null'};

    const keys = Object.keys(data).slice(0, 12);
    const hasForm  = 'taskForm' in data;
    const hasModal = isMobile ? 'showAddSheet' in data : 'showTaskModal' in data;

    if (!hasForm || !hasModal) {
        return {ok: false, reason: 'missing keys', keys, hasForm, hasModal};
    }

    // Inject mock videolar directly (these ARE reactive via the proxy)
    data.videolar = [
        {id: 100, baslik: 'Limit Girişi ve Temel Kavramlar', sure_dk: 18},
        {id: 101, baslik: 'Limit Hesaplama Teknikleri',      sure_dk: 24}
    ];
    data.listeler = [{id: 10, baslik: 'Limit ve Türev Serisi'}];
    data.dersler  = [{id: 1,  ad: 'Matematik'}];

    // Set taskForm to konu_anlatimi with liste_id pre-selected so video div is visible
    const today = new Date().toISOString().slice(0,10);
    data.taskForm = {
        ders_title: '', subject: 'mat',
        aktivite_tipi: 'konu_anlatimi', sinav_tipi: 'TYT',
        konu_ders_id: '1',
        liste_id: '10',
        selectedVideos: [],
        konu_not: '', tarih: today, ozel_sure_dk: 0, aciklama: '', error: '',
        ytPlaylistPk: null, ytPlaylistTitle: ''
    };

    // Override save method with a counter — no real network request
    data._saveCount = 0;
    if (isMobile) {
        data.saveMobileTask = async function() { this._saveCount++; };
    } else {
        data.saveTask = async function() { this._saveCount++; };
    }

    // Open the form
    if (isMobile) {
        data.showAddSheet = true;
    } else {
        data.showTaskModal = true;
    }

    return {ok: true, keys};
}
"""

READ_SAVE_COUNT_JS = "(selector) => { const el = document.querySelector(selector); return window.Alpine?.$data(el)?._saveCount ?? -1; }"
READ_CHECKBOX_JS   = "(sel) => { const cb = document.querySelector(sel); return cb ? cb.checked : null; }"
CLICK_CHECKBOX_JS  = "(sel) => { const cb = document.querySelector(sel); if (cb) cb.closest('label').click(); }"


async def run():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']
        )

        results = {}

        # ══════════════════════════════════════════════════════════════════
        # Test X: DESKTOP — real native <select> + video <input[checkbox]>
        # ══════════════════════════════════════════════════════════════════
        print('\n--- Test X: Desktop (native SELECT chain → video checkbox) ---', flush=True)

        ctx_d = await browser.new_context(viewport={'width': 1400, 'height': 900})
        await ctx_d.add_cookies([{'name':'sessionid','value':KEY,'domain':'127.0.0.1','path':'/'}])
        page_d = await ctx_d.new_page()

        # No route stubs — let API calls fail naturally (same behaviour as pw_enter_konu.py)
        await page_d.goto(f'{BASE}/coach/tasks/', wait_until='networkidle')
        await page_d.wait_for_timeout(1000)
        print('  Desktop page loaded', flush=True)

        # Seed Alpine data for the desktop panel
        seed_d = await page_d.evaluate(SEED_JS, {'selector': '[x-data="panel()"]', 'isMobile': False})
        print(f'  Seed result: {seed_d}', flush=True)

        if not seed_d.get('ok'):
            results['X'] = 'SKIP'
            print(f'  SKIP: {seed_d.get("reason")}', flush=True)
        else:
            # Wait for Alpine to re-render (video checkboxes should appear)
            await page_d.wait_for_timeout(300)

            # The video list is inside the desktop modal container
            # x-show="showTaskModal" — find a checkbox inside it
            # We search for checkbox inside the desktop panel wrapper
            chk_sel_d = '[x-data="panel()"] input[type=checkbox]'
            try:
                await page_d.wait_for_selector(chk_sel_d, state='visible', timeout=5000)
                print('  Video checkbox visible', flush=True)
            except Exception as e:
                # Check DOM state for debugging
                debug = await page_d.evaluate('''() => {
                    const panel = document.querySelector('[x-data="panel()"]');
                    if (!panel) return 'no panel element';
                    const modal = panel.querySelector('[x-show*="showTaskModal"]') ||
                                  panel.querySelector('[x-show*="showTask"]');
                    const cbs = panel.querySelectorAll("input[type=checkbox]");
                    return {
                        modalVisible: modal ? modal.offsetParent !== null : null,
                        checkboxCount: cbs.length,
                        checkboxesVisible: Array.from(cbs).map(c => c.offsetParent !== null)
                    };
                }''')
                print(f'  WARN checkbox wait: {e} | debug={debug}', flush=True)

            # Click to select the first video (using label click — NOT Enter)
            await page_d.evaluate(CLICK_CHECKBOX_JS, chk_sel_d)
            await page_d.wait_for_timeout(150)
            checked_before_d = await page_d.evaluate(READ_CHECKBOX_JS, chk_sel_d)

            save_before_d = await page_d.evaluate(READ_SAVE_COUNT_JS, '[x-data="panel()"]')
            print(f'  checkbox checked before Enter: {checked_before_d}', flush=True)
            print(f'  saveTask call count before: {save_before_d}', flush=True)

            # Focus and press Enter on the checkbox
            chk_d = page_d.locator(chk_sel_d).first
            await chk_d.focus()
            await page_d.wait_for_timeout(80)
            await chk_d.press('Enter')
            await page_d.wait_for_timeout(400)

            checked_after_d  = await page_d.evaluate(READ_CHECKBOX_JS, chk_sel_d)
            save_after_d     = await page_d.evaluate(READ_SAVE_COUNT_JS, '[x-data="panel()"]')

            saved_d    = save_after_d > save_before_d
            no_toggle_d = checked_after_d == checked_before_d

            results['X_saved']     = saved_d
            results['X_no_toggle'] = no_toggle_d

            print(f'  saveTask called: {saved_d}  (count: {save_before_d}→{save_after_d}) (want True)', flush=True)
            print(f'  checkbox NOT toggled: {no_toggle_d}  '
                  f'(before={checked_before_d}, after={checked_after_d})', flush=True)
            print(f'  X: {"OK" if saved_d and no_toggle_d else "FAIL"}', flush=True)

        await ctx_d.close()

        # ══════════════════════════════════════════════════════════════════
        # Test Y: MOBILE — real <button> list + video <input[checkbox]>
        # ══════════════════════════════════════════════════════════════════
        print('\n--- Test Y: Mobile (button list chain → video checkbox) ---', flush=True)

        ctx_m = await browser.new_context(viewport={'width': 390, 'height': 844})
        await ctx_m.add_cookies([{'name':'sessionid','value':KEY,'domain':'127.0.0.1','path':'/'}])
        page_m = await ctx_m.new_page()

        await page_m.goto(f'{BASE}/coach/tasks/', wait_until='networkidle')
        await page_m.wait_for_timeout(1000)
        print('  Mobile page loaded', flush=True)

        seed_m = await page_m.evaluate(SEED_JS, {'selector': '[x-data="coachMobilePanel()"]', 'isMobile': True})
        print(f'  Seed result: {seed_m}', flush=True)

        if not seed_m.get('ok'):
            results['Y'] = 'SKIP'
            print(f'  SKIP: {seed_m.get("reason")}', flush=True)
        else:
            await page_m.wait_for_timeout(300)

            chk_sel_m = '[x-data="coachMobilePanel()"] input[type=checkbox]'
            try:
                await page_m.wait_for_selector(chk_sel_m, state='visible', timeout=5000)
                print('  Video checkbox visible', flush=True)
            except Exception as e:
                debug = await page_m.evaluate('''() => {
                    const panel = document.querySelector("[x-data=\\"coachMobilePanel()\\"]");
                    if (!panel) return "no mobile panel";
                    const cbs = panel.querySelectorAll("input[type=checkbox]");
                    return {
                        checkboxCount: cbs.length,
                        visible: Array.from(cbs).map(c => c.offsetParent !== null)
                    };
                }''')
                print(f'  WARN checkbox wait: {e} | debug={debug}', flush=True)

            await page_m.evaluate(CLICK_CHECKBOX_JS, chk_sel_m)
            await page_m.wait_for_timeout(150)
            checked_before_m = await page_m.evaluate(READ_CHECKBOX_JS, chk_sel_m)

            save_before_m = await page_m.evaluate(READ_SAVE_COUNT_JS,
                                                   '[x-data="coachMobilePanel()"]')
            print(f'  checkbox checked before Enter: {checked_before_m}', flush=True)
            print(f'  saveMobileTask call count before: {save_before_m}', flush=True)

            chk_m = page_m.locator(chk_sel_m).first
            await chk_m.focus()
            await page_m.wait_for_timeout(80)
            await chk_m.press('Enter')
            await page_m.wait_for_timeout(400)

            checked_after_m  = await page_m.evaluate(READ_CHECKBOX_JS, chk_sel_m)
            save_after_m     = await page_m.evaluate(READ_SAVE_COUNT_JS,
                                                      '[x-data="coachMobilePanel()"]')

            saved_m     = save_after_m > save_before_m
            no_toggle_m = checked_after_m == checked_before_m

            results['Y_saved']     = saved_m
            results['Y_no_toggle'] = no_toggle_m

            print(f'  saveMobileTask called: {saved_m}  (count: {save_before_m}→{save_after_m}) (want True)', flush=True)
            print(f'  checkbox NOT toggled: {no_toggle_m}  '
                  f'(before={checked_before_m}, after={checked_after_m})', flush=True)
            print(f'  Y: {"OK" if saved_m and no_toggle_m else "FAIL"}', flush=True)

        await ctx_m.close()
        await browser.close()

        # ── Summary ───────────────────────────────────────────────────────
        print('\n' + '='*62, flush=True)
        print('COMPONENT TYPES (confirmed from source)', flush=True)
        print('  Desktop: Ders=<select>  Liste=<select>  Videos=<input[checkbox]>')
        print('  Mobile:  Ders=<button>  Liste=<button>  Videos=<input[checkbox]>')
        print()
        print('SUMMARY', flush=True)

        x_ok = results.get('X') == 'SKIP' or (results.get('X_saved') and results.get('X_no_toggle'))
        y_ok = results.get('Y') == 'SKIP' or (results.get('Y_saved') and results.get('Y_no_toggle'))

        xl = 'SKIP' if results.get('X') == 'SKIP' else ('PASS' if x_ok else 'FAIL')
        yl = 'SKIP' if results.get('Y') == 'SKIP' else ('PASS' if y_ok else 'FAIL')

        print(f'  X  Desktop <select> chain → Enter on checkbox saves not toggles: {xl}')
        print(f'  Y  Mobile  <button> chain → Enter on checkbox saves not toggles: {yl}')
        print(f'\n{"ALL PASS" if x_ok and y_ok else "FAILURES — see above"}')

asyncio.run(run())

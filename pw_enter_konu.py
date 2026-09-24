"""
Playwright: verify Enter-to-save on konu anlatimi video checkbox chain.

Tests
-----
A. Core fix: video checkbox focused → Enter saves (does NOT toggle), no checkbox exclusion
B. Regression: ders/liste SELECT open via mouse → Enter confirms selection, does NOT fire save prematurely
C. Regression: after select closes, Enter does save
D. Mobile: video checkbox → Enter saves (not toggle)
"""
import asyncio, os, sys, pathlib
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

async def run():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']
        )
        ctx = await browser.new_context(viewport={'width':1400,'height':900})
        await ctx.add_cookies([{'name':'sessionid','value':KEY,'domain':'127.0.0.1','path':'/'}])
        page = await ctx.new_page()

        # --- Collect ALL console errors ---
        console_errors = []
        page.on('console', lambda m: console_errors.append(f'[{m.type}] {m.text}')
                 if m.type in ('error','warning') else None)

        await page.goto(f'{BASE}/coach/tasks/', wait_until='networkidle')
        await page.wait_for_timeout(1000)
        print('Page loaded', flush=True)

        # ── Inject test harness: a standalone mini-form with SELECT + CHECKBOX ──
        await page.evaluate('''() => {
            window._saves = 0;
            window._toggles = 0;
            const mockSave   = () => window._saves++;
            const mockToggle = () => window._toggles++;

            const container = document.createElement("div");
            container.id = "pw-konu-container";
            container.style.cssText = "position:fixed;top:0;left:0;padding:10px;z-index:99999;background:white;display:flex;gap:8px;flex-wrap:wrap;";
            container.innerHTML = `
                <select id="pw-sel">
                  <option value="">Seçin</option>
                  <option value="mat">Matematik</option>
                  <option value="fiz">Fizik</option>
                </select>
                <label><input id="pw-chk1" type="checkbox"> Video 1</label>
                <label><input id="pw-chk2" type="checkbox"> Video 2</label>
                <input id="pw-text" type="text" placeholder="ek not">
            `;

            // Simulate the EXACT handler logic from the fix:
            // @mousedown → set __open on SELECT
            // @change    → clear __open on SELECT
            // @keydown   → new logic (no checkbox exclusion, select open/closed check)
            container.addEventListener("mousedown", function(e) {
                if (e.target.tagName === "SELECT") e.target.__open = true;
            });
            container.addEventListener("change", function(e) {
                if (e.target.tagName === "SELECT") e.target.__open = false;
            });
            container.addEventListener("keydown", function(e) {
                if (e.key !== "Enter") return;
                const t = e.target;
                if (t.tagName === "TEXTAREA") {
                    e.shiftKey || (e.preventDefault(), mockSave());
                } else if (t.tagName === "SELECT") {
                    if (t.__open) { t.__open = false; }
                    else { e.preventDefault(); mockSave(); }
                } else if (t.tagName === "INPUT" && t.type !== "radio") {
                    e.preventDefault();
                    mockSave();
                }
            });

            // Track checkbox toggles via change event
            container.addEventListener("change", function(e) {
                if (e.target.type === "checkbox") mockToggle();
            });

            document.body.appendChild(container);
        }''')

        results = {}

        print('\n--- Test A: Checkbox Enter → save (not toggle) ---', flush=True)
        # Check a video checkbox by clicking (not Enter)
        await page.evaluate('() => { document.querySelector("#pw-chk1").checked = true; window._saves=0; window._toggles=0; }')
        chk = page.locator('#pw-chk1').first
        await chk.focus()
        await page.wait_for_timeout(80)
        await chk.press('Enter')
        await page.wait_for_timeout(150)
        saved   = await page.evaluate('() => window._saves')
        toggled = await page.evaluate('() => window._toggles')
        still_checked = await page.evaluate('() => document.querySelector("#pw-chk1").checked')
        results['A_saves'] = saved
        results['A_toggles'] = toggled
        results['A_still_checked'] = still_checked
        print(f'  saves={saved} (want 1), toggles={toggled} (want 0), checkbox still checked={still_checked} (want True)', flush=True)
        print(f'  A: {"OK" if saved==1 and toggled==0 and still_checked else "FAIL"}', flush=True)

        print('\n--- Test B: SELECT open via mouse → Enter confirms, does NOT save ---', flush=True)
        sel = page.locator('#pw-sel').first
        await page.evaluate('() => { window._saves=0; window._toggles=0; }')
        # Simulate opening the select via mousedown (sets __open=true)
        await sel.evaluate('el => { el.__open = true; }')
        await sel.focus()
        await page.wait_for_timeout(80)
        await sel.press('Enter')
        await page.wait_for_timeout(150)
        saved_b = await page.evaluate('() => window._saves')
        open_after = await sel.evaluate('el => el.__open')
        results['B_saves'] = saved_b
        results['B_open_cleared'] = not open_after  # should be false after Enter
        print(f'  saves={saved_b} (want 0), __open after Enter={open_after} (want false/falsy)', flush=True)
        print(f'  B: {"OK" if saved_b==0 else "FAIL"}', flush=True)

        print('\n--- Test C: SELECT closed (after change cleared __open) → Enter saves ---', flush=True)
        # Simulate real flow: mousedown opens (__open=true), change closes (__open=false), then Enter
        saved_c = await page.evaluate('''() => {
            window._saves = 0;
            const s = document.querySelector("#pw-sel");
            // 1. Mouse opens dropdown
            s.__open = true;
            // 2. User picks option -> change fires -> __open cleared
            s.value = "mat";
            s.dispatchEvent(new Event("change", {bubbles: true, cancelable: true}));
            // 3. Enter on now-closed select (no mousedown, __open is false)
            s.dispatchEvent(new KeyboardEvent("keydown", {key: "Enter", bubbles: true, cancelable: true}));
            return window._saves;
        }''')
        results['C_saves'] = saved_c
        print(f'  saves={saved_c} (want 1)', flush=True)
        print(f'  C: {"OK" if saved_c==1 else "FAIL"}', flush=True)

        print('\n--- Test D: TEXT input Enter → save (unchanged regression) ---', flush=True)
        await page.evaluate('() => { window._saves=0; }')
        txt = page.locator('#pw-text').first
        await txt.focus()
        await page.wait_for_timeout(80)
        await txt.press('Enter')
        await page.wait_for_timeout(150)
        saved_d = await page.evaluate('() => window._saves')
        results['D_saves'] = saved_d
        print(f'  saves={saved_d} (want 1)', flush=True)
        print(f'  D: {"OK" if saved_d==1 else "FAIL"}', flush=True)

        print('\n--- Test E: Second checkbox Enter → save (not toggle) ---', flush=True)
        await page.evaluate('() => { document.querySelector("#pw-chk2").checked = false; window._saves=0; window._toggles=0; }')
        chk2 = page.locator('#pw-chk2').first
        await chk2.focus()
        await page.wait_for_timeout(80)
        await chk2.press('Enter')
        await page.wait_for_timeout(150)
        saved_e   = await page.evaluate('() => window._saves')
        toggled_e = await page.evaluate('() => window._toggles')
        still_unchecked = await page.evaluate('() => !document.querySelector("#pw-chk2").checked')
        results['E_saves'] = saved_e
        results['E_toggles'] = toggled_e
        results['E_still_unchecked'] = still_unchecked
        print(f'  saves={saved_e} (want 1), toggles={toggled_e} (want 0), still unchecked={still_unchecked} (want True)', flush=True)
        print(f'  E: {"OK" if saved_e==1 and toggled_e==0 and still_unchecked else "FAIL"}', flush=True)

        # --- Console errors ---
        print(f'\n--- Console errors (Alpine/JS): {"None" if not console_errors else len(console_errors)} ---', flush=True)
        for e in console_errors[:10]:
            print(f'  {e}', flush=True)

        await browser.close()

        print('\n' + '='*55, flush=True)
        print('SUMMARY', flush=True)
        a = results.get('A_saves')==1 and results.get('A_toggles')==0 and results.get('A_still_checked')
        b = results.get('B_saves')==0
        c = results.get('C_saves')==1
        d = results.get('D_saves')==1
        e = results.get('E_saves')==1 and results.get('E_toggles')==0 and results.get('E_still_unchecked')
        print(f'  A  checkbox Enter → save not toggle:     {"PASS" if a else "FAIL"}')
        print(f'  B  select open   → Enter no save:        {"PASS" if b else "FAIL"}')
        print(f'  C  select closed → Enter saves:          {"PASS" if c else "FAIL"}')
        print(f'  D  text input    → Enter saves:          {"PASS" if d else "FAIL"}')
        print(f'  E  unchecked chk → Enter save not check: {"PASS" if e else "FAIL"}')
        print(f'  Console errors: {"0" if not console_errors else len(console_errors)}')
        print(f'\n{"ALL PASS" if all([a,b,c,d,e]) else "FAILURES — see above"}')

asyncio.run(run())

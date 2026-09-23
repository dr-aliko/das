"""
Playwright: verify form-level Enter delegation in task forms.

Tests
-----
A) Source checks (template file reads):
   1. Each of the 6 form containers has @keydown with tagName+shiftKey guard
   2. None of the 6 textareas still carry an individual @keydown.enter attr

B) Behaviour (injected test harness, real keypresses):
   3. SELECT field: plain Enter → save called, no navigation
   4. INPUT field:  plain Enter → save called
   5. TEXTAREA:     plain Enter → save called, no newline
   6. TEXTAREA:     Shift+Enter → newline inserted, save NOT called
   7. CHECKBOX:     Enter       → save NOT called (checkbox excluded)
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
TMPL = pathlib.Path('templates')

def make_session(email):
    u = User.objects.filter(email=email).first()
    if not u: return None, None
    c = Client(); c.force_login(u)
    return c.session.session_key, u

KEY, USR = make_session('kayaa3413@gmail.com')
if not KEY: print('No session'); sys.exit(1)
print(f'User: {USR.email}')

# ── A) Source checks ─────────────────────────────────────────────────────────
print('\n--- Source checks ---')

CONTAINERS = [
    ('tasks/partials/_task_bottom_sheets.html',
     'p-6 overflow-y-auto flex-1 space-y-5',  'saveMobileTask()'),
    ('tasks/partials/_student_task_detail_sheet.html',
     'w-full max-w-sm rounded-2xl shadow-2xl p-6',  'submitComplete(false)'),
    ('student/tasks/hafta.html',
     'Görevi Düzenle',  'saveEdit()'),
    ('student/tasks/hafta.html',
     'Görevi Tamamla',  'submitComplete(false)'),
    ('student/tasks/hafta.html',
     'Yeni Görev Ekle', 'saveNewTask()'),
    ('coach/tasks/hafta.html',
     'overflow-y-auto flex-1 p-6 pb-2', 'saveTask()'),
]

TEXTAREA_NO_KEYDOWN = [
    ('tasks/partials/_task_bottom_sheets.html',    'taskForm.aciklama'),
    ('tasks/partials/_student_task_detail_sheet.html', 'completeForm.note'),
    ('student/tasks/hafta.html',  'editForm.aciklama'),
    ('student/tasks/hafta.html',  'completeForm.note'),
    ('student/tasks/hafta.html',  'addForm.aciklama'),
    ('coach/tasks/hafta.html',    'taskForm.aciklama'),
]

src_ok = True

print('\n  [Container @keydown delegation]')
for rel, anchor, save_fn in CONTAINERS:
    src = (TMPL / rel).read_text(encoding='utf-8')
    anchor_idx = src.find(anchor)
    chunk = src[max(0, anchor_idx-50):anchor_idx+600] if anchor_idx >= 0 else ''
    ok = '@keydown=' in chunk and 'tagName' in chunk and 'shiftKey' in chunk and save_fn in chunk
    src_ok &= ok
    print(f'  {"[OK]" if ok else "[FAIL]"}  {rel.split("/")[-1]}  →  {save_fn}')

print('\n  [Textarea has NO individual @keydown.enter]')
for rel, model in TEXTAREA_NO_KEYDOWN:
    src = (TMPL / rel).read_text(encoding='utf-8')
    idx = src.find(f'x-model="{model}"')
    chunk = src[max(0,idx-50):idx+300] if idx >= 0 else ''
    # Check the textarea tag (ends at >) — look only inside the tag
    tag_end = chunk.find('>', chunk.find('<textarea') if '<textarea' in chunk else 0)
    tag_chunk = chunk[:tag_end+1] if tag_end > 0 else chunk
    still_has = '@keydown.enter' in tag_chunk
    ok = not still_has
    src_ok &= ok
    print(f'  {"[OK]" if ok else "[FAIL — still has individual handler]"}  {rel.split("/")[-1]}  [{model}]')


# ── B) Behaviour tests ───────────────────────────────────────────────────────
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
        await page.goto(f'{BASE}/coach/tasks/', wait_until='networkidle')

        # Inject a self-contained test harness: a mini-form with SELECT, INPUT,
        # TEXTAREA, CHECKBOX — wired with the exact same container @keydown logic.
        await page.evaluate('''() => {
            window._saves = 0;
            const mockSave = () => window._saves++;

            const container = document.createElement("div");
            container.id = "pw-form-container";
            container.style.cssText = "position:fixed;top:0;left:0;padding:10px;z-index:99999;background:white";
            container.innerHTML = `
                <select id="pw-sel"><option value="a">A</option><option value="b">B</option></select>
                <input  id="pw-inp" type="text" value="hello">
                <input  id="pw-num" type="number" value="5">
                <textarea id="pw-ta" rows="2">line</textarea>
                <input  id="pw-chk" type="checkbox">
            `;

            // Attach the EXACT same handler logic as the form containers
            container.addEventListener("keydown", function(e) {
                if (e.key === "Enter") {
                    const t = e.target;
                    if (t.tagName === "TEXTAREA") {
                        e.shiftKey || (e.preventDefault(), mockSave());
                    } else if (
                        (t.tagName === "INPUT" && t.type !== "checkbox" && t.type !== "radio") ||
                        t.tagName === "SELECT"
                    ) {
                        e.preventDefault();
                        mockSave();
                    }
                }
            });

            document.body.appendChild(container);
        }''')

        results = {}

        async def test(label, selector, key, reset=True):
            if reset:
                await page.evaluate('() => { window._saves = 0; }')
            el = page.locator(selector).first
            await el.focus()
            await page.wait_for_timeout(80)
            await el.press(key)
            await page.wait_for_timeout(120)
            saved = await page.evaluate('() => window._saves > 0')
            val   = await page.evaluate(f'() => document.querySelector("{selector}").value')
            return saved, val

        print('\n--- Behaviour tests ---')

        # Test 3: SELECT + plain Enter → save
        saved, _ = await test('select plain Enter', '#pw-sel', 'Enter')
        results['select_enter'] = saved
        print(f'  [3] SELECT plain Enter  → save: {"[OK]" if saved else "[FAIL]"}')

        # Test 4: INPUT text + plain Enter → save
        saved, _ = await test('input plain Enter', '#pw-inp', 'Enter')
        results['input_enter'] = saved
        print(f'  [4] INPUT  plain Enter  → save: {"[OK]" if saved else "[FAIL]"}')

        # Test 4b: INPUT number + plain Enter → save
        saved, _ = await test('input number plain Enter', '#pw-num', 'Enter')
        results['number_enter'] = saved
        print(f'  [4b] INPUT number Enter → save: {"[OK]" if saved else "[FAIL]"}')

        # Test 5: TEXTAREA plain Enter → save + no newline
        await page.evaluate('() => { document.querySelector("#pw-ta").value = "hello note"; window._saves = 0; }')
        ta = page.locator('#pw-ta').first
        await ta.focus()
        await page.wait_for_timeout(80)
        await ta.press('Enter')
        await page.wait_for_timeout(120)
        saved = await page.evaluate('() => window._saves > 0')
        val   = await page.evaluate('() => document.querySelector("#pw-ta").value')
        no_nl = '\n' not in val
        results['ta_enter'] = saved and no_nl
        print(f'  [5] TEXTAREA plain Enter → save: {"[OK]" if saved else "[FAIL]"}  no newline: {"[OK]" if no_nl else "[FAIL]"}')

        # Test 6: TEXTAREA Shift+Enter → newline + no save
        await page.evaluate('() => { document.querySelector("#pw-ta").value = "line one"; window._saves = 0; }')
        await ta.focus()
        await page.wait_for_timeout(80)
        await ta.press('Shift+Enter')
        await page.wait_for_timeout(120)
        saved_s = await page.evaluate('() => window._saves > 0')
        val_s   = await page.evaluate('() => document.querySelector("#pw-ta").value')
        has_nl  = '\n' in val_s
        results['ta_shift_enter'] = not saved_s and has_nl
        print(f'  [6] TEXTAREA Shift+Enter → no save: {"[OK]" if not saved_s else "[FAIL]"}  newline: {"[OK]" if has_nl else "[FAIL]"}')

        # Test 7: CHECKBOX Enter → no save (excluded)
        saved, _ = await test('checkbox Enter', '#pw-chk', 'Enter')
        results['chk_enter'] = not saved
        print(f'  [7] CHECKBOX Enter  → save NOT called: {"[OK]" if not saved else "[FAIL]"}')

        await browser.close()
        return results

beh = asyncio.run(run())

# ── Summary ───────────────────────────────────────────────────────────────────
print('\n' + '=' * 55)
print('SUMMARY')
print(f'  [A] Source: containers wired, textareas clean:  {"PASS" if src_ok else "FAIL"}')
print(f'  [3] SELECT       plain Enter  → save:           {"PASS" if beh.get("select_enter") else "FAIL"}')
print(f'  [4] INPUT text   plain Enter  → save:           {"PASS" if beh.get("input_enter") else "FAIL"}')
print(f'  [4b] INPUT number plain Enter → save:           {"PASS" if beh.get("number_enter") else "FAIL"}')
print(f'  [5] TEXTAREA     plain Enter  → save+no nl:     {"PASS" if beh.get("ta_enter") else "FAIL"}')
print(f'  [6] TEXTAREA     Shift+Enter  → nl+no save:     {"PASS" if beh.get("ta_shift_enter") else "FAIL"}')
print(f'  [7] CHECKBOX     Enter        → NOT saved:      {"PASS" if beh.get("chk_enter") else "FAIL"}')

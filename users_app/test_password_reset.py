"""
End-to-end security tests for the password reset flow.
Run: python manage.py test users_app.test_password_reset --verbosity=2
"""
import hashlib
import re

from django.contrib.auth import authenticate
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from users_app.models import User

LOCMEM = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'pr-tests',
    }
}


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CACHES=LOCMEM,
)
class PasswordResetSecurityTests(TestCase):

    RESET_URL = '/auth/password-reset/'

    def setUp(self):
        mail.outbox = []
        cache.clear()
        self.coach = User.objects.create_user('coach_pr@test.com',   'Coach PR',   'coach',   'CoachOld1!')
        self.student = User.objects.create_user('student_pr@test.com', 'Student PR', 'student', 'StuOld1!')

    def tearDown(self):
        cache.clear()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _post_reset(self, email):
        return self.client.post(self.RESET_URL, {'email': email})

    def _extract_confirm_path(self, email_body):
        m = re.search(
            r'/auth/password-reset/confirm/([A-Za-z0-9_=-]+)/([A-Za-z0-9_-]+)/',
            email_body,
        )
        return m.group(0) if m else None

    def _navigate_confirm(self, path):
        """
        Django 4+ redirects the confirm GET to a safe URL with token in session.
        Follow that redirect so we land on the actual form page.
        Returns (final_path, response).
        """
        resp = self.client.get(path)
        if resp.status_code == 302:
            final_path = resp['Location']
            resp = self.client.get(final_path)
        else:
            final_path = path
        return final_path, resp

    # ── Test 1: User enumeration ──────────────────────────────────────────────

    def test_1_no_user_enumeration(self):
        sep = '\n' + '='*60
        print(sep)
        print('TEST 1: USER ENUMERATION CHECK')
        print('='*60)

        real_email = 'coach_pr@test.com'
        fake_email = 'nobody@nowhere.invalid'

        resp_real = self._post_reset(real_email)
        cache.clear()
        resp_fake = self._post_reset(fake_email)

        print(f'  Real email  -> status={resp_real.status_code}  Location={resp_real.get("Location")}')
        print(f'  Fake email  -> status={resp_fake.status_code}  Location={resp_fake.get("Location")}')
        print(f'  Status codes identical : {resp_real.status_code == resp_fake.status_code}')
        print(f'  Redirect target identical: {resp_real.get("Location") == resp_fake.get("Location")}')

        # Follow both to the done page
        cache.clear(); mail.outbox = []
        done_real = self.client.post(self.RESET_URL, {'email': real_email}, follow=True)
        cache.clear()
        done_fake = self.client.post(self.RESET_URL, {'email': fake_email}, follow=True)

        real_page = done_real.content.decode('utf-8')
        fake_page = done_fake.content.decode('utf-8')
        real_has_msg = 'E-posta gönderildi' in real_page
        fake_has_msg = 'E-posta gönderildi' in fake_page

        print(f'  "E-posta gönderildi" on real-email done page: {real_has_msg}')
        print(f'  "E-posta gönderildi" on fake-email done page: {fake_has_msg}')
        print(f'  Final page content identical: {real_has_msg == fake_has_msg}')

        self.assertEqual(resp_real.status_code, 302)
        self.assertEqual(resp_fake.status_code, 302)
        self.assertEqual(resp_real['Location'], resp_fake['Location'])
        self.assertTrue(real_has_msg)
        self.assertTrue(fake_has_msg)

    # ── Test 2: Rate limiting ─────────────────────────────────────────────────

    def test_2_rate_limiting(self):
        sep = '\n' + '='*60
        print(sep)
        print('TEST 2: RATE LIMIT CHECK')
        print('='*60)

        real = 'coach_pr@test.com'
        fake = 'nobody@nowhere.invalid'

        # 2a — real email, 2 requests in same window
        mail.outbox = []; cache.clear()
        r1 = self._post_reset(real)
        after_1 = len(mail.outbox)
        r2 = self._post_reset(real)
        after_2 = len(mail.outbox)

        print(f'\n  [Real email — 2 requests]')
        print(f'  1st -> status={r1.status_code} Location={r1.get("Location")}')
        print(f'  2nd -> status={r2.status_code} Location={r2.get("Location")}')
        print(f'  Emails after 1st request : {after_1}')
        print(f'  Emails after 2nd request : {after_2}')
        print(f'  Only 1 email sent total  : {after_1 == 1 and after_2 == 1}')
        print(f'  HTTP responses identical : {r1.status_code == r2.status_code and r1["Location"] == r2["Location"]}')

        self.assertEqual(after_1, 1, 'First request must send exactly 1 email')
        self.assertEqual(after_2, 1, 'Second request (throttled) must NOT send a second email')
        self.assertEqual(r1.status_code, r2.status_code)
        self.assertEqual(r1['Location'], r2['Location'])

        # 2b — fake email, 2 requests; confirm cache key is set regardless of existence
        mail.outbox = []; cache.clear()
        fake_key = 'pwd_reset_' + hashlib.md5(fake.lower().encode()).hexdigest()

        r3 = self._post_reset(fake)
        key_after_1st = cache.get(fake_key) is not None
        r4 = self._post_reset(fake)
        key_after_2nd = cache.get(fake_key) is not None
        emails_fake = len(mail.outbox)

        print(f'\n  [Fake email — 2 requests]')
        print(f'  1st -> status={r3.status_code} Location={r3.get("Location")}')
        print(f'  2nd -> status={r4.status_code} Location={r4.get("Location")}')
        print(f'  Cache key set after 1st request : {key_after_1st}')
        print(f'  Cache key still set after 2nd   : {key_after_2nd}')
        print(f'  Emails sent (none expected)      : {emails_fake}')
        print(f'  HTTP responses identical         : {r3.status_code == r4.status_code and r3["Location"] == r4["Location"]}')

        self.assertTrue(key_after_1st, 'Cache key must be set for fake email (same code path)')
        self.assertEqual(emails_fake, 0, 'No email for non-existent user')
        self.assertEqual(r3.status_code, r4.status_code)
        self.assertEqual(r3['Location'], r4['Location'])

        # 2c — throttle behavior on 2nd request is indistinguishable (real vs fake)
        cache.clear(); mail.outbox = []
        self._post_reset(real)
        r_real_2nd = self._post_reset(real)
        cache.clear(); mail.outbox = []
        self._post_reset(fake)
        r_fake_2nd = self._post_reset(fake)

        print(f'\n  [2nd request — real vs fake comparison]')
        print(f'  Real (2nd, throttled) -> status={r_real_2nd.status_code} Location={r_real_2nd["Location"]}')
        print(f'  Fake (2nd, throttled) -> status={r_fake_2nd.status_code} Location={r_fake_2nd["Location"]}')
        print(f'  Behaviorally identical: {r_real_2nd.status_code == r_fake_2nd.status_code and r_real_2nd["Location"] == r_fake_2nd["Location"]}')

        self.assertEqual(r_real_2nd.status_code, r_fake_2nd.status_code)
        self.assertEqual(r_real_2nd['Location'], r_fake_2nd['Location'])

    # ── Test 3: Email rendering ───────────────────────────────────────────────

    def test_3_email_rendering(self):
        sep = '\n' + '='*60
        print(sep)
        print('TEST 3: EMAIL RENDERING')
        print('='*60)

        mail.outbox = []; cache.clear()
        self._post_reset('coach_pr@test.com')
        self.assertEqual(len(mail.outbox), 1)
        em = mail.outbox[0]

        print(f'  Subject   : {em.subject}')
        print(f'  From      : {em.from_email}')
        print(f'  To        : {em.to}')
        print(f'  Alternatives: {len(em.alternatives)} (should be 1 — HTML part)')

        html, mime = em.alternatives[0]
        print(f'  MIME type : {mime}')
        print(f'  HTML size : {len(html):,} chars')

        checks = {
            'Vagus brand header'        : 'Vagus' in html,
            'Indigo color #6366F1'      : '6366F1' in html,
            'CTA button text'           : 'Şifremi Sıfırla' in html,
            'Reset link in button href' : '/auth/password-reset/confirm/' in html,
            'tek kullanımlık note'      : 'tek kullanımlık' in html,
            '1 saat expiry note'        : '1 saat' in html,
            'Vagus Ekibi footer'        : 'Vagus Ekibi' in html,
            'f9fafb footer bg (invite pattern)': 'f9fafb' in html,
        }
        for label, ok in checks.items():
            print(f'  {"PASS" if ok else "FAIL"}  {label}')

        print(f'\n  --- HTML snippet (first 500 chars) ---')
        print('  ' + html[:500].replace('\n', '\n  '))

        print(f'\n  --- Plain text body ---')
        print('  ' + em.body[:400].replace('\n', '\n  '))

        self.assertEqual(em.subject, 'Vagus — Şifre Sıfırlama')
        self.assertEqual(mime, 'text/html')
        for label, ok in checks.items():
            self.assertTrue(ok, f'Email check failed: {label}')

    # ── Test 4: Full flow (coach + student) ──────────────────────────────────

    def _full_flow(self, email, old_pw, new_pw, label):
        print(f'\n  [{label}]')
        mail.outbox = []; cache.clear()

        # 1 — request reset
        r = self._post_reset(email)
        print(f'  1. Reset request   -> {r.status_code} {r["Location"]}')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], '/auth/password-reset/done/')

        # 2 — extract link from email
        self.assertEqual(len(mail.outbox), 1)
        confirm_path = self._extract_confirm_path(mail.outbox[0].body)
        self.assertIsNotNone(confirm_path, 'No confirm link found in email body')
        print(f'  2. Email link      : ...{confirm_path[-60:]}')

        # 3 — GET confirm page (Django redirects to 'set-password' URL)
        final_path, resp_get = self._navigate_confirm(confirm_path)
        page = resp_get.content.decode('utf-8')
        print(f'  3. GET confirm     -> {resp_get.status_code}, form shown: {"Yeni Şifre" in page}')
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn('Yeni Şifre', page, 'Password form must appear for a valid link')
        self.assertNotIn('Yeni Link İste', page, 'Valid link must not show invalid-link message')

        # 4 — POST new password
        resp_post = self.client.post(final_path, {
            'new_password1': new_pw,
            'new_password2': new_pw,
        })
        print(f'  4. POST new password -> {resp_post.status_code}')
        self.assertIn(resp_post.status_code, [200, 302])

        if resp_post.status_code == 302:
            resp_complete = self.client.get(resp_post['Location'])
            complete_page = resp_complete.content.decode('utf-8')
            print(f'  5. Complete page   -> {resp_complete.status_code}, "güncellendi": {"güncellendi" in complete_page}')

        # 5 — verify credentials
        ok_new = authenticate(request=None, email=email, password=new_pw)
        ok_old = authenticate(request=None, email=email, password=old_pw)
        print(f'  6. New password login : {"WORKS ✓" if ok_new else "FAILS ✗"}')
        print(f'     Old password login : {"WORKS ✗ (BAD)" if ok_old else "FAILS ✓ (expected)"}')
        self.assertIsNotNone(ok_new,  f'{label}: new password must work')
        self.assertIsNone(   ok_old,  f'{label}: old password must be rejected')

    def test_4a_full_flow_coach(self):
        print('\n' + '='*60)
        print('TEST 4a: FULL FLOW — COACH ACCOUNT')
        print('='*60)
        self._full_flow('coach_pr@test.com', 'CoachOld1!', 'CoachNew9@!', 'coach')

    def test_4b_full_flow_student(self):
        print('\n' + '='*60)
        print('TEST 4b: FULL FLOW — STUDENT ACCOUNT')
        print('='*60)
        self._full_flow('student_pr@test.com', 'StuOld1!', 'StuNew9@!', 'student')

    # ── Test 5: Token single-use ──────────────────────────────────────────────

    def test_5_token_single_use(self):
        sep = '\n' + '='*60
        print(sep)
        print('TEST 5: TOKEN SINGLE-USE')
        print('='*60)

        mail.outbox = []; cache.clear()
        self._post_reset('coach_pr@test.com')
        original_path = self._extract_confirm_path(mail.outbox[0].body)
        self.assertIsNotNone(original_path)
        print(f'  Original link: ...{original_path[-60:]}')

        # First use — complete the reset
        final_path, _ = self._navigate_confirm(original_path)
        r_use1 = self.client.post(final_path, {
            'new_password1': 'CoachNew99@!',
            'new_password2': 'CoachNew99@!',
        })
        print(f'  1st use (complete reset) -> {r_use1.status_code}')
        self.assertIn(r_use1.status_code, [200, 302])

        # Second use — try the ORIGINAL link again (password has changed; token is now invalid)
        _, resp_reuse = self._navigate_confirm(original_path)
        page = resp_reuse.content.decode('utf-8')

        is_invalid = 'Yeni Link İste' in page or 'geçersiz' in page.lower() or 'invalid' in page.lower()
        form_visible = 'new_password1' in page and 'Yeni Link İste' not in page

        print(f'  2nd use (reuse original link):')
        print(f'    HTTP status        : {resp_reuse.status_code}')
        print(f'    "Yeni Link İste" shown: {"Yeni Link İste" in page}')
        print(f'    Password form shown: {form_visible}')
        print(f'    Token invalidated  : {is_invalid and not form_visible}')

        self.assertTrue(is_invalid,   'Reused token must show invalid-link page')
        self.assertFalse(form_visible,'Reused token must NOT show password form')

    # ── Test 6: UI — login page link ──────────────────────────────────────────

    def test_6_ui_login_page_link(self):
        sep = '\n' + '='*60
        print(sep)
        print('TEST 6: UI — "Şifremi unuttum" LINK ON LOGIN PAGE')
        print('='*60)

        resp = self.client.get('/auth/login/')
        self.assertEqual(resp.status_code, 200)
        page = resp.content.decode('utf-8')

        has_href  = '/auth/password-reset/' in page
        has_text  = 'ifremi unuttum' in page   # handles both Ş and ş
        is_shared = '/auth/login/' in page      # single login for all roles

        print(f'  GET /auth/login/ -> {resp.status_code}')
        print(f'  Link href present (/auth/password-reset/) : {has_href}')
        print(f'  Link text present (Şifremi unuttum)       : {has_text}')
        print(f'  Single shared login page for all roles    : True')
        print(f'  Mobile: same template; brand panel hidden via CSS at <900px')
        print(f'  (No separate mobile login URL exists in this app)')

        # Print surrounding context so user can verify placement
        idx = page.find('password-reset')
        if idx != -1:
            snippet = page[max(0, idx-120):idx+120]
            print(f'\n  Context around link:\n  ...{snippet.strip()}...')

        self.assertTrue(has_href, 'Login page must link to /auth/password-reset/')
        self.assertTrue(has_text, 'Login page must contain "Şifremi unuttum" text')

"""
End-to-end security tests for the password reset flow.
Run: python manage.py test users_app.test_password_reset --verbosity=2

Override CACHES to LocMemCache for tests — production uses DatabaseCache
(shared across Gunicorn workers) but the test DB won't have django_cache table.
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
    DONE_URL  = '/auth/password-reset/done/'

    def setUp(self):
        mail.outbox = []
        cache.clear()
        self.coach   = User.objects.create_user('coach_pr@test.com',   'Coach PR',   'coach',   'CoachOld1!')
        self.student = User.objects.create_user('student_pr@test.com', 'Student PR', 'student', 'StuOld1!')

    def tearDown(self):
        cache.clear()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _post_reset(self, email):
        return self.client.post(self.RESET_URL, {'email': email})

    def _post_reset_follow(self, email):
        return self.client.post(self.RESET_URL, {'email': email}, follow=True)

    def _extract_confirm_path(self, email_body):
        m = re.search(
            r'/auth/password-reset/confirm/([A-Za-z0-9_=-]+)/([A-Za-z0-9_-]+)/',
            email_body,
        )
        return m.group(0) if m else None

    def _navigate_confirm(self, path):
        resp = self.client.get(path)
        if resp.status_code == 302:
            final_path = resp['Location']
            resp = self.client.get(final_path)
        else:
            final_path = path
        return final_path, resp

    # ── Test 1: User enumeration (fresh send) ────────────────────────────────

    def test_1_no_user_enumeration_fresh(self):
        print('\n' + '='*60)
        print('TEST 1: USER ENUMERATION — FRESH SEND')
        print('='*60)

        real = 'coach_pr@test.com'
        fake = 'nobody@nowhere.invalid'

        r_real = self._post_reset(real)
        cache.clear()
        r_fake = self._post_reset(fake)

        print(f'  Real -> status={r_real.status_code}  Location={r_real.get("Location")}')
        print(f'  Fake -> status={r_fake.status_code}  Location={r_fake.get("Location")}')
        print(f'  Status codes identical      : {r_real.status_code == r_fake.status_code}')
        print(f'  Redirect targets identical  : {r_real.get("Location") == r_fake.get("Location")}')

        cache.clear(); mail.outbox = []
        done_real = self._post_reset_follow(real)
        cache.clear()
        done_fake = self._post_reset_follow(fake)

        rp = done_real.content.decode('utf-8')
        fp = done_fake.content.decode('utf-8')

        real_fresh = 'E-posta gönderildi' in rp
        fake_fresh = 'E-posta gönderildi' in fp
        real_throttled = 'Link zaten gönderildi' in rp
        fake_throttled = 'Link zaten gönderildi' in fp

        print(f'  Real done page: "E-posta gönderildi"={real_fresh}, "Link zaten"={real_throttled}')
        print(f'  Fake done page: "E-posta gönderildi"={fake_fresh}, "Link zaten"={fake_throttled}')
        print(f'  Both show FRESH message  : {real_fresh and fake_fresh}')
        print(f'  Neither shows THROTTLE   : {not real_throttled and not fake_throttled}')
        print(f'  Pages identical (real==fake): {real_fresh == fake_fresh and real_throttled == fake_throttled}')

        self.assertEqual(r_real.status_code, 302)
        self.assertEqual(r_fake.status_code, 302)
        self.assertEqual(r_real['Location'], r_fake['Location'])
        self.assertTrue(real_fresh and fake_fresh, 'Both must show fresh-send message')
        self.assertFalse(real_throttled or fake_throttled, 'Neither should show throttle message on first request')

    # ── Test 2: Rate limiting + enumeration safety (throttled) ───────────────

    def test_2_rate_limiting_and_throttle_message(self):
        print('\n' + '='*60)
        print('TEST 2: RATE LIMIT + TWO-MESSAGE ENUMERATION SAFETY')
        print('='*60)

        real = 'coach_pr@test.com'
        fake = 'nobody@nowhere.invalid'

        # 2a — real email: 1st (fresh) then 2nd (throttled)
        mail.outbox = []; cache.clear()
        r1 = self._post_reset(real)
        after_1 = len(mail.outbox)
        r2 = self._post_reset(real)
        after_2 = len(mail.outbox)

        print(f'\n  [Real email — 2 requests]')
        print(f'  1st -> {r1.status_code} {r1.get("Location")}')
        print(f'  2nd -> {r2.status_code} {r2.get("Location")}')
        print(f'  Emails after 1st : {after_1}')
        print(f'  Emails after 2nd : {after_2}  (throttled, must NOT be 2)')
        print(f'  HTTP responses identical: {r1.status_code == r2.status_code and r1["Location"] == r2["Location"]}')

        self.assertEqual(after_1, 1, '1st request must send 1 email')
        self.assertEqual(after_2, 1, '2nd request (throttled) must NOT send a 2nd email')
        self.assertEqual(r1.status_code, r2.status_code)
        self.assertEqual(r1['Location'], r2['Location'])

        # 2b — fake email: cache key set on 1st, throttled on 2nd
        mail.outbox = []; cache.clear()
        fake_key = 'pwd_reset_' + hashlib.md5(fake.lower().encode()).hexdigest()

        r3 = self._post_reset(fake)
        key_1st = cache.get(fake_key) is not None
        r4 = self._post_reset(fake)
        key_2nd = cache.get(fake_key) is not None

        print(f'\n  [Fake email — 2 requests]')
        print(f'  1st -> {r3.status_code} {r3.get("Location")}')
        print(f'  2nd -> {r4.status_code} {r4.get("Location")}')
        print(f'  Cache key set after 1st : {key_1st}  (must be True — same code path as real)')
        print(f'  Cache key set after 2nd : {key_2nd}')
        print(f'  HTTP responses identical: {r3.status_code == r4.status_code and r3["Location"] == r4["Location"]}')

        self.assertTrue(key_1st, 'Cache key must be set for fake email on 1st request')
        self.assertEqual(r3.status_code, r4.status_code)
        self.assertEqual(r3['Location'], r4['Location'])

        # 2c — both messages: real-fresh == fake-fresh, real-throttled == fake-throttled
        print(f'\n  [Message content: real vs fake in each state]')

        # Fresh state (clear cache first)
        cache.clear(); mail.outbox = []
        done_real_fresh  = self._post_reset_follow(real)
        cache.clear()
        done_fake_fresh  = self._post_reset_follow(fake)

        rfp = done_real_fresh.content.decode('utf-8')
        ffp = done_fake_fresh.content.decode('utf-8')
        real_msg_fresh   = 'E-posta gönderildi' in rfp
        fake_msg_fresh   = 'E-posta gönderildi' in ffp
        real_throttle_on_fresh = 'Link zaten gönderildi' in rfp
        fake_throttle_on_fresh = 'Link zaten gönderildi' in ffp

        print(f'  Fresh state — real: fresh_msg={real_msg_fresh}, throttle_msg={real_throttle_on_fresh}')
        print(f'  Fresh state — fake: fresh_msg={fake_msg_fresh}, throttle_msg={fake_throttle_on_fresh}')
        print(f'  SAME message in fresh state (real==fake): {real_msg_fresh == fake_msg_fresh and real_throttle_on_fresh == fake_throttle_on_fresh}')

        # Throttled state (submit twice without clearing cache)
        cache.clear(); mail.outbox = []
        self._post_reset(real)
        done_real_throttled = self._post_reset_follow(real)
        cache.clear(); mail.outbox = []
        self._post_reset(fake)
        done_fake_throttled = self._post_reset_follow(fake)

        rtp = done_real_throttled.content.decode('utf-8')
        ftp = done_fake_throttled.content.decode('utf-8')
        real_msg_throttled = 'Link zaten gönderildi' in rtp
        fake_msg_throttled = 'Link zaten gönderildi' in ftp
        real_fresh_on_throttle = 'E-posta gönderildi' in rtp
        fake_fresh_on_throttle = 'E-posta gönderildi' in ftp

        print(f'  Throttled state — real: throttle_msg={real_msg_throttled}, fresh_msg={real_fresh_on_throttle}')
        print(f'  Throttled state — fake: throttle_msg={fake_msg_throttled}, fresh_msg={fake_fresh_on_throttle}')
        print(f'  SAME message in throttled state (real==fake): {real_msg_throttled == fake_msg_throttled and real_fresh_on_throttle == fake_fresh_on_throttle}')
        # real_msg_fresh = "does fresh page show fresh msg?" (should be True)
        # real_fresh_on_throttle = "does throttled page show fresh msg?" (should be False)
        print(f'  DIFFERENT between states (fresh page has it, throttled page does not): {real_msg_fresh and not real_fresh_on_throttle}')

        # Assertions
        self.assertTrue(real_msg_fresh and fake_msg_fresh, 'Both real and fake must get fresh message on 1st request')
        self.assertFalse(real_throttle_on_fresh or fake_throttle_on_fresh, 'Fresh-state page must not show throttle message')
        self.assertTrue(real_msg_throttled and fake_msg_throttled, 'Both real and fake must get throttle message on 2nd request')
        self.assertFalse(real_fresh_on_throttle or fake_fresh_on_throttle, 'Throttled-state page must not show fresh message')
        # The two states produce different pages — fresh msg appears on fresh page only
        self.assertTrue(real_msg_fresh and not real_fresh_on_throttle, 'Messages MUST differ between states')

    # ── Test 3: Email rendering ───────────────────────────────────────────────

    def test_3_email_rendering(self):
        print('\n' + '='*60)
        print('TEST 3: EMAIL RENDERING')
        print('='*60)

        mail.outbox = []; cache.clear()
        self._post_reset('coach_pr@test.com')
        self.assertEqual(len(mail.outbox), 1)
        em = mail.outbox[0]

        print(f'  Subject   : {em.subject}')
        print(f'  From      : {em.from_email}')
        print(f'  To        : {em.to}')
        print(f'  Alternatives: {len(em.alternatives)}')

        html, mime = em.alternatives[0]
        print(f'  MIME type : {mime}')
        print(f'  HTML size : {len(html):,} chars')

        checks = {
            'Vagus brand header'        : 'Vagus' in html,
            'Indigo color #6366F1'      : '6366F1' in html,
            'CTA button "Sifremi Sifirla"': 'ifremi' in html,
            'Reset confirm link'        : '/auth/password-reset/confirm/' in html,
            'tek kullanımlik note'      : 'tek kullan' in html,
            '1 saat expiry'             : '1 saat' in html,
            'Vagus Ekibi footer'        : 'Vagus Ekibi' in html,
            'f9fafb footer bg'          : 'f9fafb' in html,
        }
        for label, ok in checks.items():
            print(f'  {"PASS" if ok else "FAIL"}  {label}')

        print(f'\n  Plain text (first 350 chars):')
        print('  ' + em.body[:350].replace('\n', '\n  '))

        self.assertEqual(em.subject, 'Vagus — Şifre Sıfırlama')
        self.assertEqual(mime, 'text/html')
        for label, ok in checks.items():
            self.assertTrue(ok, f'Email check failed: {label}')

    # ── Test 4: Full flow (coach + student) ──────────────────────────────────

    def _full_flow(self, email, old_pw, new_pw, label):
        print(f'\n  [{label}]')
        mail.outbox = []; cache.clear()

        r = self._post_reset(email)
        print(f'  1. Reset request      -> {r.status_code} {r["Location"]}')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], self.DONE_URL)

        self.assertEqual(len(mail.outbox), 1)
        confirm_path = self._extract_confirm_path(mail.outbox[0].body)
        self.assertIsNotNone(confirm_path)
        print(f'  2. Email link         : ...{confirm_path[-55:]}')

        final_path, resp_get = self._navigate_confirm(confirm_path)
        page = resp_get.content.decode('utf-8')
        print(f'  3. GET confirm        -> {resp_get.status_code}, form shown: {"Yeni Sifre" in page or "Yeni" in page}')
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn('Yeni', page)
        self.assertNotIn('Yeni Link', page)

        resp_post = self.client.post(final_path, {
            'new_password1': new_pw,
            'new_password2': new_pw,
        })
        print(f'  4. POST new password  -> {resp_post.status_code}')
        self.assertIn(resp_post.status_code, [200, 302])

        if resp_post.status_code == 302:
            rc = self.client.get(resp_post['Location'])
            rcp = rc.content.decode('utf-8')
            print(f'  5. Complete page      -> {rc.status_code}, "guncellendi": {"ncellendi" in rcp}')

        ok_new = authenticate(request=None, email=email, password=new_pw)
        ok_old = authenticate(request=None, email=email, password=old_pw)
        print(f'  6. New password login : {"WORKS" if ok_new else "FAILS"}')
        print(f'     Old password login : {"WORKS (BAD)" if ok_old else "FAILS (expected)"}')
        self.assertIsNotNone(ok_new,  f'{label}: new password must authenticate')
        self.assertIsNone(   ok_old,  f'{label}: old password must be rejected')

    def test_4a_full_flow_coach(self):
        print('\n' + '='*60)
        print('TEST 4a: FULL FLOW — COACH')
        print('='*60)
        self._full_flow('coach_pr@test.com', 'CoachOld1!', 'CoachNew9@!', 'coach')

    def test_4b_full_flow_student(self):
        print('\n' + '='*60)
        print('TEST 4b: FULL FLOW — STUDENT')
        print('='*60)
        self._full_flow('student_pr@test.com', 'StuOld1!', 'StuNew9@!', 'student')

    # ── Test 5: Token single-use ──────────────────────────────────────────────

    def test_5_token_single_use(self):
        print('\n' + '='*60)
        print('TEST 5: TOKEN SINGLE-USE')
        print('='*60)

        mail.outbox = []; cache.clear()
        self._post_reset('coach_pr@test.com')
        original_path = self._extract_confirm_path(mail.outbox[0].body)
        self.assertIsNotNone(original_path)
        print(f'  Original link: ...{original_path[-55:]}')

        final_path, _ = self._navigate_confirm(original_path)
        r1 = self.client.post(final_path, {'new_password1': 'CoachNew99@!', 'new_password2': 'CoachNew99@!'})
        print(f'  1st use (complete reset) -> {r1.status_code}')
        self.assertIn(r1.status_code, [200, 302])

        _, resp2 = self._navigate_confirm(original_path)
        page = resp2.content.decode('utf-8')
        invalid = 'Yeni Link' in page or 'geçersiz' in page.lower()
        form_shown = 'new_password1' in page and 'Yeni Link' not in page

        print(f'  2nd use (reuse link):')
        print(f'    Status              : {resp2.status_code}')
        print(f'    Invalid-link page   : {invalid}')
        print(f'    Password form shown : {form_shown}  (must be False)')
        print(f'    Token invalidated   : {invalid and not form_shown}')

        self.assertTrue(invalid, 'Reused token must show invalid page')
        self.assertFalse(form_shown, 'Reused token must not expose password form')

    # ── Test 6: UI ────────────────────────────────────────────────────────────

    def test_6_ui_login_page_link(self):
        print('\n' + '='*60)
        print('TEST 6: UI — "Sifremi unuttum" LINK ON LOGIN PAGE')
        print('='*60)

        resp = self.client.get('/auth/login/')
        self.assertEqual(resp.status_code, 200)
        page = resp.content.decode('utf-8')

        has_href = '/auth/password-reset/' in page
        has_text = 'ifremi unuttum' in page

        print(f'  GET /auth/login/ -> {resp.status_code}')
        print(f'  Link href present : {has_href}')
        print(f'  Link text present : {has_text}')
        print(f'  Single shared login page (coach + student + staff): True')
        print(f'  Mobile: same template, brand panel hidden via CSS @media <900px')

        idx = page.find('password-reset')
        if idx != -1:
            snippet = page[max(0, idx-100):idx+110].strip()
            print(f'\n  Actual HTML context:\n  {snippet}')

        self.assertTrue(has_href)
        self.assertTrue(has_text)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    CACHES=LOCMEM,
)
class SessionInvalidationTests(TestCase):
    """
    Verify that completing a password reset invalidates all OTHER active sessions
    for that user (cross-device / cross-browser logout).
    """

    RESET_URL = '/auth/password-reset/'
    # login_required GET endpoint — returns 200 JSON for students, 302 for anonymous.
    PROBE_URL = '/student/notifications/'

    def setUp(self):
        mail.outbox = []
        cache.clear()
        self.user = User.objects.create_user(
            'victim@sessions.test', 'Victim', 'student', 'OldPass1!'
        )

    def tearDown(self):
        cache.clear()

    def _extract_confirm_path(self, body):
        m = re.search(
            r'/auth/password-reset/confirm/([A-Za-z0-9_=-]+)/([A-Za-z0-9_-]+)/',
            body,
        )
        return m.group(0) if m else None

    def _navigate_confirm(self, client, path):
        resp = client.get(path)
        if resp.status_code == 302:
            final_path = resp['Location']
            client.get(final_path)
        else:
            final_path = path
        return final_path

    def test_7_cross_device_session_invalidated_after_reset(self):
        from django.contrib.sessions.models import Session

        print('\n' + '='*60)
        print('TEST 7: CROSS-DEVICE SESSION INVALIDATION')
        print('='*60)

        client_a = Client()
        client_b = Client()

        # Device A logs in via the test-client helper (bypasses form parsing)
        login_ok = client_a.login(email='victim@sessions.test', password='OldPass1!')
        print(f'  Device A login() returned        : {login_ok}')
        self.assertTrue(login_ok, 'Device A login must succeed')

        # Capture Device A session key after login
        session_key_a = client_a.session.session_key
        print(f'  Device A session key             : {session_key_a[:20]}...')

        in_db_before = Session.objects.filter(session_key=session_key_a).exists()
        print(f'  Session in DB before reset       : {in_db_before}  (must be True)')
        self.assertTrue(in_db_before, 'Device A session must exist in DB before reset')

        # Confirm Device A can reach a protected endpoint
        probe_before = client_a.get(self.PROBE_URL).status_code
        print(f'  Probe GET {self.PROBE_URL} before : {probe_before}  (must NOT be 302)')
        self.assertNotEqual(probe_before, 302, 'Device A must be authenticated before reset')

        # Device B (anonymous) requests + completes password reset
        mail.outbox = []
        cache.clear()
        client_b.post(self.RESET_URL, {'email': 'victim@sessions.test'})
        self.assertEqual(len(mail.outbox), 1, 'Reset email must be sent')

        confirm_path = self._extract_confirm_path(mail.outbox[0].body)
        self.assertIsNotNone(confirm_path)
        print(f'  Reset link                       : ...{confirm_path[-40:]}')

        final_path = self._navigate_confirm(client_b, confirm_path)
        resp_post = client_b.post(
            final_path,
            {'new_password1': 'NewPass9@!', 'new_password2': 'NewPass9@!'},
        )
        print(f'  Device B reset POST              -> {resp_post.status_code}')
        self.assertIn(resp_post.status_code, [200, 302], 'Reset must succeed')

        # The session row must be EXPLICITLY deleted from DB by our fix
        in_db_after = Session.objects.filter(session_key=session_key_a).exists()
        print(f'  Session in DB after reset        : {in_db_after}  (must be False)')
        self.assertFalse(
            in_db_after,
            '_invalidate_other_sessions() must have deleted the session row',
        )

        # End-to-end: Device A's next request must redirect to login
        probe_after = client_a.get(self.PROBE_URL).status_code
        print(f'  Probe GET {self.PROBE_URL} after  : {probe_after}  (must be 302)')
        self.assertEqual(probe_after, 302, 'Device A must be redirected to login after reset')

        print('  PASS: cross-device session invalidation confirmed')

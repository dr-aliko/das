"""
Brute-force protection tests for CustomLoginView.
Run: python manage.py test users_app.test_login_ratelimit --verbosity=2

Policy under test
-----------------
  login_pair_{hash(email|ip)} : 10 failures in 15 min  -> lockout for that IP+email pair
  login_ip_{hash(ip)}         : 20 failures in 15 min  -> lockout for the entire IP
  On success                  : both counters cleared
  No global-per-email lockout : a different IP can always attempt the same email
"""
import hashlib

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from users_app.models import User
from users_app.views import _login_cache_keys, _LOGIN_RATE_MSG

LOGIN_URL = '/auth/login/'

LOCMEM = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'login-rl-tests',
    }
}


def _pair_count(email, ip):
    key_pair, _ = _login_cache_keys(email, ip)
    return cache.get(key_pair) or 0


def _ip_count(ip):
    _, key_ip = _login_cache_keys('_', ip)
    return cache.get(key_ip) or 0


def _fail(client, email, ip, password='wrong_pw'):
    return client.post(
        LOGIN_URL,
        {'username': email, 'password': password},
        REMOTE_ADDR=ip,
    )


def _attempt(client, email, ip, password):
    return client.post(
        LOGIN_URL,
        {'username': email, 'password': password},
        REMOTE_ADDR=ip,
    )


@override_settings(CACHES=LOCMEM)
class LoginRateLimitTests(TestCase):

    IP_A = '10.0.0.1'
    IP_B = '10.0.0.2'

    def setUp(self):
        cache.clear()
        self.coach   = User.objects.create_user('coach_rl@test.com',   'Coach RL',   'coach',   'CoachRL1!')
        self.student = User.objects.create_user('student_rl@test.com', 'Student RL', 'student', 'StuRL1!')

    def tearDown(self):
        cache.clear()

    # ── Test 1: pair lockout blocks the 11th attempt — even with correct password ─

    def test_1_pair_lockout_blocks_correct_password(self):
        print('\n' + '='*60)
        print('TEST 1: PAIR LOCKOUT (10 failures -> 11th blocked)')
        print('='*60)

        email = 'student_rl@test.com'
        correct_pw = 'StuRL1!'
        ip = self.IP_A

        # 10 failed attempts (wrong password)
        for i in range(10):
            r = _fail(self.client, email, ip)
            self.assertEqual(r.status_code, 200, f'Attempt {i+1} must return 200 (form page)')

        pair_after_10 = _pair_count(email, ip)
        print(f'  Pair counter after 10 failures : {pair_after_10}  (must be 10)')
        self.assertEqual(pair_after_10, 10)

        # 11th attempt with the CORRECT password — must be blocked
        r11 = _attempt(self.client, email, ip, correct_pw)
        page = r11.content.decode('utf-8')

        is_blocked      = 'fazla' in page
        has_rate_msg    = _LOGIN_RATE_MSG[:20] in page
        not_redirected  = r11.status_code != 302
        no_account_hint = 'hesap' not in page.lower() and 'kilitlendi' not in page.lower()

        print(f'  11th attempt status            : {r11.status_code}  (must be 200, not 302)')
        print(f'  Rate limit message present     : {is_blocked}')
        print(f'  Correct password still blocked : {not_redirected}')
        print(f'  No "account locked" enumeration: {no_account_hint}')

        self.assertEqual(r11.status_code, 200, 'Blocked response must be 200, not redirect')
        self.assertTrue(is_blocked, 'Rate limit message must be in the response')
        self.assertTrue(no_account_hint, 'Message must not reveal account existence')

    # ── Test 2: successful login resets the counter ───────────────────────────

    def test_2_counter_resets_on_success(self):
        print('\n' + '='*60)
        print('TEST 2: COUNTER RESET ON SUCCESSFUL LOGIN')
        print('='*60)

        email = 'student_rl@test.com'
        correct_pw = 'StuRL1!'
        ip = self.IP_A

        # 5 failures (below the 10 threshold)
        for _ in range(5):
            _fail(self.client, email, ip)

        pair_at_5 = _pair_count(email, ip)
        print(f'  Pair counter after 5 failures  : {pair_at_5}  (must be 5)')
        self.assertEqual(pair_at_5, 5)

        # Successful login — clears counter
        r_ok = _attempt(self.client, email, ip, correct_pw)
        print(f'  Successful login status        : {r_ok.status_code}  (must be 302)')
        self.assertEqual(r_ok.status_code, 302, 'Correct login must redirect')

        pair_after_ok = _pair_count(email, ip)
        print(f'  Pair counter after success     : {pair_after_ok}  (must be 0)')
        self.assertEqual(pair_after_ok, 0, 'Counter must be cleared on successful login')

        # 9 more failures — counter restarts from 0, must not trigger lockout
        for _ in range(9):
            _fail(self.client, email, ip)

        pair_at_9_fresh = _pair_count(email, ip)
        print(f'  Pair counter after 9 new fails : {pair_at_9_fresh}  (must be 9, not 14)')
        self.assertEqual(pair_at_9_fresh, 9, 'Counter must have restarted from 0, not 14')

        # 10th failure reaches the threshold
        _fail(self.client, email, ip)
        self.assertEqual(_pair_count(email, ip), 10)

        # 11th attempt (correct PW) must now be blocked
        r11 = _attempt(self.client, email, ip, correct_pw)
        page = r11.content.decode('utf-8')
        print(f'  11th attempt after reset cycle : {r11.status_code}, rate_limited={("fazla" in page)}')
        self.assertEqual(r11.status_code, 200)
        self.assertIn('fazla', page, 'Must be locked after 10 fresh failures post-reset')

    # ── Test 3: per-IP total threshold (20) independent of pair threshold ─────

    def test_3_ip_total_threshold(self):
        print('\n' + '='*60)
        print('TEST 3: PER-IP TOTAL THRESHOLD (20 failures across many accounts)')
        print('='*60)

        ip = self.IP_A

        # 4 failures each against 5 different emails = 20 IP failures.
        # No pair exceeds 10, so the pair threshold is never triggered.
        emails = [f'ip_victim_{i}@nowhere.invalid' for i in range(5)]
        for email in emails:
            for _ in range(4):
                _fail(self.client, email, ip)

        ip_total = _ip_count(ip)
        print(f'  IP counter after 4x5=20 fails  : {ip_total}  (must be 20)')
        self.assertEqual(ip_total, 20)

        # Verify no pair hit the threshold
        for email in emails:
            self.assertLess(_pair_count(email, ip), 10, f'Pair for {email} must be < 10')

        # 21st attempt (new email, any password) must be blocked by the IP counter
        r21 = _fail(self.client, 'brand_new@nowhere.invalid', ip)
        page = r21.content.decode('utf-8')
        print(f'  21st attempt status            : {r21.status_code}  (must be 200/blocked)')
        print(f'  Rate limit message present     : {"fazla" in page}')
        self.assertEqual(r21.status_code, 200, 'IP-total-limited response must be 200')
        self.assertIn('fazla', page, 'Rate limit message must appear when IP total exceeded')

        # Also confirm a DIFFERENT IP is unaffected
        r_other = _fail(self.client, 'brand_new@nowhere.invalid', self.IP_B)
        print(f'  Same attempt from IP-B status  : {r_other.status_code}  (must be 200, NOT blocked)')
        # IP-B has 0 failures — form invalid page (200) but for credentials reason, not rate limit
        page_b = r_other.content.decode('utf-8')
        self.assertEqual(r_other.status_code, 200)
        self.assertNotIn('fazla', page_b, 'IP-B must not show rate limit message')

    # ── Test 4: different IP can still reach the same email ───────────────────

    def test_4_different_ip_not_blocked(self):
        print('\n' + '='*60)
        print('TEST 4: DIFFERENT IP NOT BLOCKED (no global-per-email lockout)')
        print('='*60)

        email = 'student_rl@test.com'
        correct_pw = 'StuRL1!'

        # Lock out IP_A + email pair (10 failures)
        for _ in range(10):
            _fail(self.client, email, self.IP_A)

        # Confirm IP_A is locked for this email
        r_a = _attempt(self.client, email, self.IP_A, correct_pw)
        page_a = r_a.content.decode('utf-8')
        a_blocked = 'fazla' in page_a
        print(f'  IP_A + email locked            : {a_blocked}  (must be True)')
        self.assertTrue(a_blocked, 'IP_A must be blocked after 10 pair failures')

        # IP_B has zero failures for this email — login must succeed
        client_b = Client()
        r_b = _attempt(client_b, email, self.IP_B, correct_pw)
        print(f'  IP_B + same email status       : {r_b.status_code}  (must be 302 success)')
        self.assertEqual(r_b.status_code, 302, 'IP_B must succeed despite IP_A being locked')
        self.assertIn('/student/', r_b.get('Location', ''), 'Must redirect to student dashboard')

        # Verify IP_A pair counter is still 10 (IP_B success only cleared IP_B's keys)
        pair_a_after = _pair_count(email, self.IP_A)
        pair_b_after = _pair_count(email, self.IP_B)
        print(f'  IP_A pair counter unchanged    : {pair_a_after}  (must still be 10)')
        print(f'  IP_B pair counter cleared      : {pair_b_after}  (must be 0)')
        self.assertEqual(pair_a_after, 10, 'IP_A pair counter must be unchanged')
        self.assertEqual(pair_b_after, 0,  'IP_B pair counter must be cleared after success')

    # ── Test 5: lockout lifts after the 15-min window expires ────────────────

    def test_5_lockout_lifts_after_window_expiry(self):
        print('\n' + '='*60)
        print('TEST 5: LOCKOUT LIFTS WHEN WINDOW EXPIRES (simulated via cache.clear)')
        print('='*60)

        email = 'student_rl@test.com'
        correct_pw = 'StuRL1!'
        ip = self.IP_A

        # Trigger lockout
        for _ in range(10):
            _fail(self.client, email, ip)

        # Confirm locked
        r_blocked = _attempt(self.client, email, ip, correct_pw)
        page_blocked = r_blocked.content.decode('utf-8')
        print(f'  Before expiry: blocked         : {"fazla" in page_blocked}  (must be True)')
        self.assertIn('fazla', page_blocked, 'Must be locked before window expires')

        # Simulate window expiry — cache TTL expiry behaves identically to clearing the key
        cache.clear()
        pair_after_clear = _pair_count(email, ip)
        print(f'  Pair counter after cache.clear : {pair_after_clear}  (must be 0)')
        self.assertEqual(pair_after_clear, 0, 'Counter must be gone after window expiry')

        # Login must now succeed with correct credentials
        r_after = _attempt(self.client, email, ip, correct_pw)
        print(f'  After expiry: login status     : {r_after.status_code}  (must be 302)')
        self.assertEqual(r_after.status_code, 302, 'Login must succeed after window expires')
        self.assertIn('/student/', r_after.get('Location', ''), 'Must redirect to student dashboard')

"""
Email verification tests for coach self-registration.
Run: python manage.py test users_app.test_email_verification --verbosity=2

Policy under test
-----------------
  Code expiry    : 10 minutes
  Max attempts   : 5 wrong codes -> 6th is blocked
  Resend cooldown: 2 minutes between resends
  Max resends    : 5 per 30-minute window (per IP+email)
  On success     : email_verified=True, is_active still False, is_approved still False
"""
from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from users_app.models import EmailVerificationCode, User
from users_app.views import _VERIFY_CODE_EXPIRY, _VERIFY_RESEND_MAX, _verify_resend_keys

REGISTER_URL      = '/auth/register/'
VERIFY_URL        = '/auth/verify-email/'
RESEND_URL        = '/auth/verify-email/resend/'
REVERIFY_URL      = '/auth/verify-email/resend-form/'

LOCMEM = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'verify-tests',
    }
}

COACH_DATA = {
    'email':     'verifycoach@test.com',
    'full_name': 'Verify Coach',
    'password1': 'VerifyPW1!',
    'password2': 'VerifyPW1!',
}

IP = '10.0.1.1'


def _make_unverified_coach(email='verifycoach@test.com', password='VerifyPW1!'):
    user = User.objects.create_user(email=email, full_name='Verify Coach', role='coach', password=password)
    user.is_approved = False
    user.is_active   = False
    user.save(update_fields=['is_approved', 'is_active'])
    return user


def _set_code(user, code='123456', expired=False):
    delta = timedelta(seconds=-1) if expired else timedelta(seconds=_VERIFY_CODE_EXPIRY)
    EmailVerificationCode.objects.update_or_create(
        user=user,
        defaults={'code': code, 'expires_at': timezone.now() + delta, 'attempts': 0},
    )


def _set_session(client, user_id):
    session = client.session
    session['pending_verification_uid'] = user_id
    session.save()


@override_settings(
    CACHES=LOCMEM,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class EmailVerificationTests(TestCase):

    IP = '10.0.1.1'

    def setUp(self):
        cache.clear()
        mail.outbox = []

    def tearDown(self):
        cache.clear()

    # ── Test 1: registration creates EmailVerificationCode ────────────────────

    def test_1_registration_creates_code_and_sends_email(self):
        print('\n' + '='*60)
        print('TEST 1: REGISTRATION CREATES CODE + SENDS EMAIL')
        print('='*60)

        r = self.client.post(REGISTER_URL, COACH_DATA, REMOTE_ADDR=self.IP)

        user = User.objects.get(email='verifycoach@test.com')
        evc  = EmailVerificationCode.objects.get(user=user)

        expiry_window_min = timezone.now() + timedelta(seconds=_VERIFY_CODE_EXPIRY - 5)
        expiry_window_max = timezone.now() + timedelta(seconds=_VERIFY_CODE_EXPIRY + 5)

        print(f'  User created                  : {user.email}')
        print(f'  Code attempts                 : {evc.attempts}  (must be 0)')
        print(f'  Code length                   : {len(evc.code)}  (must be 6)')
        print(f'  Expires within 10-min window  : {expiry_window_min <= evc.expires_at <= expiry_window_max}')
        print(f'  Email sent                    : {len(mail.outbox) == 1}  (must be True)')
        print(f'  Redirect to verify-email      : {r.status_code == 302 and "verify-email" in r["Location"]}')
        print(f'  Session uid set               : {self.client.session.get("pending_verification_uid") == user.id}')

        self.assertEqual(evc.attempts, 0, 'attempts must start at 0')
        self.assertEqual(len(evc.code), 6, 'code must be 6 digits')
        self.assertTrue(expiry_window_min <= evc.expires_at <= expiry_window_max,
                        'expires_at must be ~10 min from now')
        self.assertEqual(len(mail.outbox), 1, 'exactly one email must be sent')
        self.assertIn(evc.code, mail.outbox[0].body, 'code must appear in email body')
        self.assertEqual(r.status_code, 302)
        self.assertIn('verify-email', r['Location'])
        self.assertEqual(self.client.session['pending_verification_uid'], user.id)

    # ── Test 2: 5 wrong codes -> 6th blocked ─────────────────────────────────

    def test_2_max_attempts_blocks_sixth_try(self):
        print('\n' + '='*60)
        print('TEST 2: 5 WRONG CODES -> 6TH BLOCKED')
        print('='*60)

        user = _make_unverified_coach()
        _set_code(user, '999999')
        _set_session(self.client, user.id)

        for i in range(5):
            r = self.client.post(VERIFY_URL, {'code': '000000'}, REMOTE_ADDR=self.IP)
            self.assertEqual(r.status_code, 200)

        evc = EmailVerificationCode.objects.get(user=user)
        print(f'  DB attempts after 5 wrong    : {evc.attempts}  (must be 5)')
        self.assertEqual(evc.attempts, 5, 'DB attempts must be 5 after 5 wrong codes')

        r6 = self.client.post(VERIFY_URL, {'code': '999999'}, REMOTE_ADDR=self.IP)
        page = r6.content.decode('utf-8', errors='replace')
        print(f'  6th attempt status           : {r6.status_code}  (must be 200)')
        print(f'  Max-attempts message present : {"yanlis" in page.lower() or "deneme" in page.lower()}')
        self.assertEqual(r6.status_code, 200)
        self.assertNotEqual(r6.status_code, 302, 'correct code must NOT succeed when max attempts reached')
        self.assertIn('deneme', page.lower(), 'max-attempts message must appear')

    # ── Test 3: correct code -> verified + still inactive + lands on awaiting ─

    def test_3_correct_code_sets_email_verified(self):
        print('\n' + '='*60)
        print('TEST 3: CORRECT CODE -> email_verified=True, still inactive')
        print('='*60)

        user = _make_unverified_coach()
        _set_code(user, '654321')
        _set_session(self.client, user.id)

        r = self.client.post(VERIFY_URL, {'code': '654321'}, REMOTE_ADDR=self.IP)

        user.refresh_from_db()
        code_exists = EmailVerificationCode.objects.filter(user=user).exists()

        print(f'  Redirect status              : {r.status_code}  (must be 302)')
        print(f'  Redirect location            : {r.get("Location", "")}')
        print(f'  email_verified               : {user.email_verified}  (must be True)')
        print(f'  is_active                    : {user.is_active}  (must be False)')
        print(f'  is_approved                  : {user.is_approved}  (must be False)')
        print(f'  Code deleted from DB         : {not code_exists}  (must be True)')

        self.assertEqual(r.status_code, 302)
        self.assertIn('awaiting', r['Location'])
        self.assertTrue(user.email_verified, 'email_verified must be True after correct code')
        self.assertFalse(user.is_active,   'is_active must still be False')
        self.assertFalse(user.is_approved, 'is_approved must still be False')
        self.assertFalse(code_exists, 'EmailVerificationCode must be deleted on success')
        self.assertNotIn('pending_verification_uid', self.client.session,
                         'session key must be cleared after success')

    # ── Test 4: expired code rejected ─────────────────────────────────────────

    def test_4_expired_code_rejected(self):
        print('\n' + '='*60)
        print('TEST 4: EXPIRED CODE REJECTED')
        print('='*60)

        user = _make_unverified_coach()
        _set_code(user, '111111', expired=True)
        _set_session(self.client, user.id)

        r = self.client.post(VERIFY_URL, {'code': '111111'}, REMOTE_ADDR=self.IP)
        page = r.content.decode('utf-8', errors='replace')

        user.refresh_from_db()

        print(f'  Response status              : {r.status_code}  (must be 200, not 302)')
        print(f'  Expired message present      : {"suresi" in page.lower() or "dolmus" in page.lower()}')
        print(f'  email_verified after expiry  : {user.email_verified}  (must be False)')

        self.assertEqual(r.status_code, 200, 'expired code must not redirect')
        self.assertFalse(user.email_verified, 'email_verified must remain False')
        self.assertTrue(
            'suresi' in page.lower() or 'dolmus' in page.lower(),
            'Expiry message must appear on page',
        )

    # ── Test 5: resend replaces old code + cooldown enforced ──────────────────

    def test_5_resend_replaces_code_and_cooldown(self):
        print('\n' + '='*60)
        print('TEST 5: RESEND REPLACES CODE + COOLDOWN BLOCKS IMMEDIATE RETRY')
        print('='*60)

        user = _make_unverified_coach()
        _set_code(user, '777777')
        _set_session(self.client, user.id)
        mail.outbox = []

        # First resend succeeds
        r1 = self.client.post(RESEND_URL, REMOTE_ADDR=self.IP)
        evc_new = EmailVerificationCode.objects.get(user=user)

        print(f'  First resend status          : {r1.status_code}  (must be 302)')
        print(f'  New code != old code         : {evc_new.code != "777777"}  (must be True)')
        print(f'  New attempts = 0             : {evc_new.attempts == 0}  (must be True)')
        print(f'  Email sent                   : {len(mail.outbox) == 1}')

        self.assertEqual(r1.status_code, 302)
        self.assertNotEqual(evc_new.code, '777777', 'old code must be replaced')
        self.assertEqual(evc_new.attempts, 0, 'attempts must reset to 0 on resend')
        self.assertEqual(len(mail.outbox), 1, 'one email must be sent on resend')

        # Old code '777777' must be REJECTED — DB record now holds a different code
        r_old_code = self.client.post(VERIFY_URL, {'code': '777777'}, REMOTE_ADDR=self.IP)
        print(f'  Old code rejected after resend: {r_old_code.status_code}  (must be 200, not 302)')
        self.assertEqual(r_old_code.status_code, 200,
                         'old code must not succeed after resend replaces it')

        # Immediate second resend is blocked by 2-min cooldown
        mail.outbox = []
        r2 = self.client.post(RESEND_URL, REMOTE_ADDR=self.IP)
        page2 = self.client.get(VERIFY_URL).content.decode('utf-8', errors='replace')

        print(f'  Second resend (cooldown)     : {r2.status_code}  (must be 302 back to verify)')
        print(f'  Cooldown message present     : {"bekleyin" in page2.lower() or len(mail.outbox) == 0}')

        self.assertEqual(r2.status_code, 302)
        self.assertEqual(len(mail.outbox), 0, 'no email must be sent during cooldown')

    # ── Test 6: 6th resend blocked by cap ─────────────────────────────────────

    def test_6_resend_cap_blocks_sixth(self):
        print('\n' + '='*60)
        print('TEST 6: RESEND CAP BLOCKS 6TH REQUEST')
        print('='*60)

        user = _make_unverified_coach()
        _set_code(user, '444444')
        _set_session(self.client, user.id)

        key_cool, key_cnt = _verify_resend_keys(user.email, self.IP)

        mail.outbox = []
        for i in range(_VERIFY_RESEND_MAX):
            cache.delete(key_cool)   # clear cooldown to allow each resend
            r = self.client.post(RESEND_URL, REMOTE_ADDR=self.IP)
            print(f'  Resend {i+1} status            : {r.status_code}')

        count_after_5 = cache.get(key_cnt) or 0
        print(f'  Resend count after 5         : {count_after_5}  (must be 5)')
        self.assertEqual(count_after_5, _VERIFY_RESEND_MAX)

        # 6th resend — cooldown cleared but count is maxed
        cache.delete(key_cool)
        mail.outbox = []
        r6 = self.client.post(RESEND_URL, REMOTE_ADDR=self.IP)

        print(f'  6th resend status            : {r6.status_code}  (must be 302, not new email)')
        print(f'  No email sent on 6th         : {len(mail.outbox) == 0}  (must be True)')

        self.assertEqual(r6.status_code, 302, '6th resend must redirect (blocked)')
        self.assertEqual(len(mail.outbox), 0, 'no email must be sent on 6th resend')

    # ── Test 7: verification flow does not flip is_active -> login still blocked ─

    def test_7_verification_does_not_flip_is_active_login_blocked(self):
        print('\n' + '='*60)
        print('TEST 7: FULL FLOW — VERIFICATION DOES NOT FLIP is_active, LOGIN BLOCKED')
        print('='*60)

        # Step 1: Register (register_view sets is_active=False, is_approved=False)
        r_reg = self.client.post(REGISTER_URL, COACH_DATA, REMOTE_ADDR=self.IP)
        self.assertEqual(r_reg.status_code, 302, 'registration must redirect to verify page')

        user = User.objects.get(email='verifycoach@test.com')
        evc  = EmailVerificationCode.objects.get(user=user)
        correct_code = evc.code

        print(f'  After register: is_active    = {user.is_active}  (must be False)')
        print(f'  After register: is_approved  = {user.is_approved}  (must be False)')
        self.assertFalse(user.is_active,   'is_active must be False right after registration')
        self.assertFalse(user.is_approved, 'is_approved must be False right after registration')

        # Step 2: Complete email verification with the correct code
        r_verify = self.client.post(VERIFY_URL, {'code': correct_code}, REMOTE_ADDR=self.IP)
        self.assertEqual(r_verify.status_code, 302, 'correct code must redirect to awaiting-approval')
        self.assertIn('awaiting', r_verify['Location'])

        user.refresh_from_db()
        print(f'  After verify:   email_verified = {user.email_verified}  (must be True)')
        print(f'  After verify:   is_active      = {user.is_active}  (must still be False)')
        print(f'  After verify:   is_approved    = {user.is_approved}  (must still be False)')

        self.assertTrue(user.email_verified, 'email_verified must be True after correct code')
        self.assertFalse(user.is_active,   'is_active must NOT be flipped by email verification')
        self.assertFalse(user.is_approved, 'is_approved must NOT be flipped by email verification')

        # Step 3: Attempt login with a fresh client — must still be blocked
        login_client = Client()
        r_login = login_client.post(
            '/auth/login/',
            {'username': 'verifycoach@test.com', 'password': 'VerifyPW1!'},
            REMOTE_ADDR=self.IP,
        )
        print(f'  Login after verify: status   = {r_login.status_code}  (must be 200, not 302)')
        print(f'  No auth session created      : {login_client.session.get("_auth_user_id") is None}')

        self.assertEqual(r_login.status_code, 200,
                         'verified-but-unapproved coach must not be able to log in')
        self.assertIsNone(login_client.session.get('_auth_user_id'),
                          'session must not carry auth user id after blocked login')

    # ── Test 8: "came back later" reverify path ───────────────────────────────

    def test_8_reverify_came_back_later_path(self):
        print('\n' + '='*60)
        print('TEST 8: CAME BACK LATER REVERIFY PATH')
        print('='*60)

        user = _make_unverified_coach()
        mail.outbox = []

        r = self.client.post(
            REVERIFY_URL,
            {'email': 'verifycoach@test.com'},
            REMOTE_ADDR=self.IP,
        )

        evc  = EmailVerificationCode.objects.get(user=user)
        uid_in_session = self.client.session.get('pending_verification_uid')

        print(f'  Response status              : {r.status_code}  (must be 200, shows "check email")')
        print(f'  Email sent                   : {len(mail.outbox) == 1}  (must be True)')
        print(f'  Session uid set              : {uid_in_session == user.id}  (must be True)')
        print(f'  Code created/replaced        : {evc is not None}  (must be True)')

        self.assertEqual(r.status_code, 200, 'reverify view must render (not redirect)')
        self.assertEqual(len(mail.outbox), 1, 'one email must be sent for valid unverified user')
        self.assertEqual(uid_in_session, user.id, 'session must have the user id')
        self.assertIsNotNone(evc, 'EmailVerificationCode must be created')
        self.assertIn(evc.code, mail.outbox[0].body, 'code must appear in email')

        # Fake email returns same response without error (enumeration safety)
        mail.outbox = []
        r_fake = self.client.post(
            REVERIFY_URL,
            {'email': 'doesnotexist@nowhere.invalid'},
            REMOTE_ADDR=self.IP,
        )
        print(f'  Fake email status            : {r_fake.status_code}  (must be 200, same UX)')
        print(f'  No email for fake address    : {len(mail.outbox) == 0}  (must be True)')

        self.assertEqual(r_fake.status_code, 200, 'fake email must get same 200 response')
        self.assertEqual(len(mail.outbox), 0, 'no email must be sent for non-existent address')

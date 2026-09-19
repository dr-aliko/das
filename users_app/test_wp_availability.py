"""
Rate-limit + debounce tests for the WordPress availability toggle.
Run: python manage.py test users_app.test_wp_availability --verbosity=2

Server-side policy under test
------------------------------
  wp_avail_cd_{user_pk}  : 2-second cooldown per coach
  First request           : calls WP API, sets cooldown, saves wp_is_available
  Subsequent requests (within cooldown): HTTP 429, no WP API call, no DB change
  After cooldown expires  : next request goes through normally
"""
import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from users_app.models import User
from users_app.views import _wp_avail_cooldown_key, _WP_AVAIL_COOLDOWN

# The view does a deferred `from .services.wordpress import …` inside the
# function body, so patch must target the name in the service module (the
# canonical location Python resolves on each call), not users_app.views.
_WP_PATCH = 'users_app.services.wordpress.update_wp_coach_availability'

URL = '/profil/wp-availability/'

LOCMEM = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'wp-avail-tests',
    }
}


def _post(client, is_available):
    return client.post(
        URL,
        data=json.dumps({'is_available': is_available}),
        content_type='application/json',
    )


def _data(resp):
    return json.loads(resp.content)


@override_settings(CACHES=LOCMEM)
class WpAvailabilityRateLimitTests(TestCase):

    def setUp(self):
        cache.clear()
        self.coach = User.objects.create_user(
            email='wp_rl_coach@test.com',
            full_name='WP Coach',
            role='coach',
            password='testpass123',
        )
        self.coach.is_approved = True
        self.coach.wordpress_post_id = 9999
        self.coach.wp_is_available = False
        self.coach.save(update_fields=['is_approved', 'wordpress_post_id', 'wp_is_available'])

        self.client = Client()
        self.client.login(username='wp_rl_coach@test.com', password='testpass123')

    # ──────────────────────────────────────────────────────────────────────────

    def test_1_unauthenticated_gets_403(self):
        print()
        print('=' * 60)
        print('TEST 1: UNAUTHENTICATED REQUEST -> 403')
        print('=' * 60)
        anon = Client()
        resp = anon.post(URL, data='{}', content_type='application/json')
        print(f'  Status: {resp.status_code}  (must be 302 or 403)')
        self.assertIn(resp.status_code, (302, 403))
        print('  PASS')

    def test_2_no_wp_post_id_gets_403(self):
        print()
        print('=' * 60)
        print('TEST 2: COACH WITHOUT wordpress_post_id -> 403')
        print('=' * 60)
        coach2 = User.objects.create_user(
            email='no_wp_id@test.com', full_name='No WP', role='coach', password='testpass123'
        )
        coach2.is_approved = True
        coach2.save(update_fields=['is_approved'])
        c = Client()
        c.login(username='no_wp_id@test.com', password='testpass123')
        resp = _post(c, True)
        print(f'  Status: {resp.status_code}  (must be 403)')
        self.assertEqual(resp.status_code, 403)
        print('  PASS')

    @patch(_WP_PATCH)
    def test_3_first_request_calls_wp_api(self, mock_wp):
        print()
        print('=' * 60)
        print('TEST 3: FIRST REQUEST -> WP API CALLED, DB UPDATED')
        print('=' * 60)
        mock_wp.return_value = (True, None)

        resp = _post(self.client, True)
        data = _data(resp)

        print(f'  Status          : {resp.status_code}  (must be 200)')
        print(f'  ok              : {data["ok"]}  (must be True)')
        print(f'  WP API calls    : {mock_wp.call_count}  (must be 1)')
        print(f'  WP call args    : wp_post_id={mock_wp.call_args[0][0]}, is_available={mock_wp.call_args[0][1]}')

        self.coach.refresh_from_db()
        print(f'  DB wp_is_available: {self.coach.wp_is_available}  (must be True)')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertEqual(mock_wp.call_count, 1)
        self.assertEqual(mock_wp.call_args[0], (9999, True))
        self.assertTrue(self.coach.wp_is_available)
        print('  PASS')

    @patch(_WP_PATCH)
    def test_4_rapid_5_clicks_only_1_wp_call(self, mock_wp):
        print()
        print('=' * 60)
        print('TEST 4: 5 RAPID REQUESTS -> ONLY 1 WP API CALL (rate limit)')
        print('=' * 60)
        mock_wp.return_value = (True, None)

        results = []
        # Toggle alternately to simulate rapid clicking: F→T→F→T→F→T
        for i in range(5):
            desired = (i % 2 == 0)   # True, False, True, False, True
            resp = _post(self.client, desired)
            results.append({
                'click': i + 1,
                'desired': desired,
                'status': resp.status_code,
                'ok': _data(resp).get('ok'),
                'error': _data(resp).get('error', ''),
            })

        print(f'  {"Click":<6} {"Desired":<8} {"Status":<8} {"ok":<6} {"Notes"}')
        print(f'  {"-"*5:<6} {"-"*7:<8} {"-"*6:<8} {"-"*5:<6} {"-"*30}')
        for r in results:
            note = '>> first through' if r['click'] == 1 else '>> 429 rate-limited' if r['status'] == 429 else ''
            print(f'  {r["click"]:<6} {str(r["desired"]):<8} {r["status"]:<8} {str(r["ok"]):<6} {note}')

        wp_calls = mock_wp.call_count
        print()
        print(f'  Total WP API calls: {wp_calls}  (must be 1)')
        print(f'  Requests blocked  : {sum(1 for r in results if r["status"] == 429)}  (must be 4)')

        self.assertEqual(wp_calls, 1)
        self.assertEqual(results[0]['status'], 200)
        self.assertTrue(results[0]['ok'])
        for r in results[1:]:
            self.assertEqual(r['status'], 429)
            self.assertFalse(r['ok'])
        print('  PASS')

    @patch(_WP_PATCH)
    def test_5_cooldown_expires_allows_next_request(self, mock_wp):
        print()
        print('=' * 60)
        print('TEST 5: COOLDOWN EXPIRES -> NEXT REQUEST GOES THROUGH')
        print('=' * 60)
        mock_wp.return_value = (True, None)

        # First request goes through
        r1 = _post(self.client, True)
        print(f'  Request 1 status: {r1.status_code}  (must be 200)')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(mock_wp.call_count, 1)

        # Second request within cooldown
        r2 = _post(self.client, False)
        print(f'  Request 2 status: {r2.status_code}  (must be 429, within cooldown)')
        self.assertEqual(r2.status_code, 429)
        self.assertEqual(mock_wp.call_count, 1)

        # Manually expire cooldown by deleting the cache key
        cooldown_key = _wp_avail_cooldown_key(self.coach.pk)
        cache.delete(cooldown_key)
        print(f'  Cooldown key deleted (simulates {_WP_AVAIL_COOLDOWN}s passing)')

        # Third request after cooldown — must go through
        r3 = _post(self.client, False)
        print(f'  Request 3 status: {r3.status_code}  (must be 200, cooldown expired)')
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(mock_wp.call_count, 2)

        self.coach.refresh_from_db()
        print(f'  DB wp_is_available: {self.coach.wp_is_available}  (must be False, from request 3)')
        self.assertFalse(self.coach.wp_is_available)
        print('  PASS')

    @patch(_WP_PATCH)
    def test_6_wp_api_failure_reverts_db_and_returns_error(self, mock_wp):
        print()
        print('=' * 60)
        print('TEST 6: WP API FAILURE -> DB NOT CHANGED, 502 RETURNED')
        print('=' * 60)
        mock_wp.return_value = (False, 'Web sitesi güncellenemedi, tekrar deneyin.')

        resp = _post(self.client, True)
        data = _data(resp)

        print(f'  Status  : {resp.status_code}  (must be 502)')
        print(f'  ok      : {data["ok"]}  (must be False)')
        print(f'  error   : {data["error"]}')

        self.coach.refresh_from_db()
        print(f'  DB wp_is_available: {self.coach.wp_is_available}  (must still be False, unchanged)')

        self.assertEqual(resp.status_code, 502)
        self.assertFalse(data['ok'])
        self.assertFalse(self.coach.wp_is_available)
        print('  PASS')

    @patch(_WP_PATCH)
    def test_7_cooldown_set_even_on_wp_failure(self, mock_wp):
        print()
        print('=' * 60)
        print('TEST 7: WP FAILURE STILL SETS COOLDOWN (no retry spam)')
        print('=' * 60)
        mock_wp.return_value = (False, 'Web sitesi güncellenemedi, tekrar deneyin.')

        r1 = _post(self.client, True)
        r2 = _post(self.client, True)

        print(f'  Request 1 (WP fail) status: {r1.status_code}  (must be 502)')
        print(f'  Request 2 (cooldown)  status: {r2.status_code}  (must be 429)')
        print(f'  WP API calls total: {mock_wp.call_count}  (must be 1, not 2)')

        self.assertEqual(r1.status_code, 502)
        self.assertEqual(r2.status_code, 429)
        self.assertEqual(mock_wp.call_count, 1)
        print('  PASS')

    @patch(_WP_PATCH)
    def test_8_429_response_includes_retry_after(self, mock_wp):
        print()
        print('=' * 60)
        print('TEST 8: 429 RESPONSE INCLUDES retry_after FOR CLIENT AUTO-RETRY')
        print('=' * 60)
        mock_wp.return_value = (True, None)

        # First request goes through; second gets 429
        _post(self.client, True)
        r = _post(self.client, False)
        data = _data(r)

        print(f'  Status           : {r.status_code}  (must be 429)')
        print(f'  ok               : {data["ok"]}  (must be False)')
        print(f'  retry_after      : {data.get("retry_after")}  (must be {_WP_AVAIL_COOLDOWN})')
        print(f'  error present    : {"error" in data}  (must be True)')

        self.assertEqual(r.status_code, 429)
        self.assertFalse(data['ok'])
        self.assertEqual(data.get('retry_after'), _WP_AVAIL_COOLDOWN)
        self.assertIn('error', data)
        print('  PASS')

    @patch(_WP_PATCH)
    def test_9_auto_retry_eventual_consistency(self, mock_wp):
        """
        Simulates the client-side auto-retry sequence from the server's POV:
          1. Request A fires (from Tab A) -> goes through, cooldown set
          2. Request B fires (from Tab B) -> 429
          3. Client JS waits for retry_after seconds, then re-sends request B
          4. Request B retry -> goes through, DB updated to B's desired state
        Final state must reflect the LAST toggle, not be silently dropped.
        """
        print()
        print('=' * 60)
        print('TEST 9: AUTO-RETRY EVENTUAL CONSISTENCY (multi-tab scenario)')
        print('=' * 60)
        mock_wp.return_value = (True, None)

        # Tab A: sets available=True
        rA = _post(self.client, True)
        self.coach.refresh_from_db()
        print(f'  Tab A (True)   : status={rA.status_code}  DB={self.coach.wp_is_available}')
        self.assertEqual(rA.status_code, 200)
        self.assertTrue(self.coach.wp_is_available)

        # Tab B fires immediately (within cooldown) -> 429
        rB1 = _post(self.client, False)
        data_429 = _data(rB1)
        print(f'  Tab B (False, 1st try): status={rB1.status_code}  retry_after={data_429.get("retry_after")}')
        self.assertEqual(rB1.status_code, 429)
        self.assertEqual(data_429.get('retry_after'), _WP_AVAIL_COOLDOWN)

        # DB still reflects Tab A's successful write
        self.coach.refresh_from_db()
        print(f'  DB after Tab B 429: {self.coach.wp_is_available}  (still True from Tab A)')
        self.assertTrue(self.coach.wp_is_available)

        # Simulate client auto-retry: cooldown expires, Tab B retries
        cooldown_key = _wp_avail_cooldown_key(self.coach.pk)
        cache.delete(cooldown_key)
        print(f'  Cooldown expired (simulated)')

        rB2 = _post(self.client, False)
        self.coach.refresh_from_db()
        print(f'  Tab B (False, retry): status={rB2.status_code}  DB={self.coach.wp_is_available}')
        self.assertEqual(rB2.status_code, 200)
        self.assertFalse(self.coach.wp_is_available)

        wp_calls = mock_wp.call_count
        print(f'  Total WP API calls: {wp_calls}  (must be 2: Tab A + Tab B retry)')
        self.assertEqual(wp_calls, 2)
        print(f'  Final DB state: {self.coach.wp_is_available}  (must be False = Tab B\'s intent)')
        self.assertFalse(self.coach.wp_is_available)
        print('  Final intended state DID reach WordPress after auto-retry: CONFIRMED')
        print('  PASS')

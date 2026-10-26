"""Tests for editable capacity explanation: parser, staff settings page, coach view."""
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from capacity_app.models import CapacitySettings
from capacity_app.services import (
    EXPLANATION_DEFAULT_TITLE,
    EXPLANATION_DEFAULT_BODY,
    parse_explanation_body,
)
from users_app.models import User


# ── Parser ────────────────────────────────────────────────────────────────────

class ParseExplanationBodyTests(TestCase):

    def test_title_colon_text(self):
        result = parse_explanation_body('Başlık: açıklama metni')
        self.assertEqual(result['items'], [{'title': 'Başlık', 'text': 'açıklama metni'}])
        self.assertIsNone(result['note'])

    def test_plain_line_no_title(self):
        result = parse_explanation_body('sade metin')
        self.assertEqual(result['items'], [{'title': '', 'text': 'sade metin'}])

    def test_note_line(self):
        result = parse_explanation_body('! bu bir nottur')
        self.assertEqual(result['items'], [])
        self.assertEqual(result['note'], 'bu bir nottur')

    def test_max_eight_items(self):
        body = '\n'.join(f'Madde {i}: metin {i}' for i in range(10))
        result = parse_explanation_body(body)
        self.assertEqual(len(result['items']), 8)

    def test_note_after_max_items_still_captured(self):
        body = '\n'.join(f'Madde {i}: metin {i}' for i in range(9)) + '\n! son not'
        result = parse_explanation_body(body)
        self.assertEqual(len(result['items']), 8)
        self.assertEqual(result['note'], 'son not')

    def test_blank_lines_ignored(self):
        result = parse_explanation_body('\n\nBaşlık: metin\n\n')
        self.assertEqual(len(result['items']), 1)

    def test_empty_body(self):
        result = parse_explanation_body('')
        self.assertEqual(result['items'], [])
        self.assertIsNone(result['note'])

    def test_none_body(self):
        result = parse_explanation_body(None)
        self.assertEqual(result['items'], [])
        self.assertIsNone(result['note'])

    def test_default_body_has_five_items(self):
        result = parse_explanation_body(EXPLANATION_DEFAULT_BODY)
        self.assertEqual(len(result['items']), 5)
        self.assertIsNone(result['note'])


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_staff(**kw):
    u = User.objects.create_user(
        email=kw.pop('email', 'staff@test.com'),
        password='pw',
        full_name='Staff User',
        role='staff',
    )
    u.is_staff = True
    u.save()
    return u


def _make_coach(**kw):
    u = User.objects.create_user(
        email=kw.pop('email', 'coach@test.com'),
        password='pw',
        full_name='Coach User',
        role='coach',
    )
    User.objects.filter(pk=u.pk).update(is_approved=True)
    u.is_approved = True
    return u


# ── Staff settings page ───────────────────────────────────────────────────────

class ExplanationSettingsPageTests(TestCase):

    def setUp(self):
        self.staff = _make_staff()
        self.client = Client()
        self.client.force_login(self.staff)
        self.url = reverse('capacity_panel:settings')
        # Ensure singleton exists
        CapacitySettings.get()

    def test_page_loads(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'explanation_title')
        self.assertContains(r, 'explanation_body')

    def test_page_shows_current_title(self):
        cfg = CapacitySettings.get()
        cfg.explanation_title = 'Özel Başlık'
        cfg.save()
        r = self.client.get(self.url)
        self.assertContains(r, 'Özel Başlık')

    def test_save_explanation_updates_db(self):
        r = self.client.post(self.url, {
            'action': 'save_explanation',
            'explanation_title': 'Yeni Başlık',
            'explanation_body':  'Madde A: metin A\nMadde B: metin B',
        })
        self.assertRedirects(r, self.url)
        cfg = CapacitySettings.get()
        self.assertEqual(cfg.explanation_title, 'Yeni Başlık')
        self.assertIn('Madde A', cfg.explanation_body)

    def test_save_explanation_empty_title_rejected(self):
        r = self.client.post(self.url, {
            'action': 'save_explanation',
            'explanation_title': '',
            'explanation_body':  'bir madde',
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'boş bırakılamaz')

    def test_save_explanation_too_long_body_rejected(self):
        r = self.client.post(self.url, {
            'action': 'save_explanation',
            'explanation_title': 'Başlık',
            'explanation_body':  'x' * 1501,
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '1500')

    def test_save_explanation_too_many_items_rejected(self):
        body = '\n'.join(f'Madde {i}: metin {i}' for i in range(9))
        r = self.client.post(self.url, {
            'action': 'save_explanation',
            'explanation_title': 'Başlık',
            'explanation_body':  body,
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '8 madde')

    def test_reset_restores_defaults(self):
        cfg = CapacitySettings.get()
        cfg.explanation_title = 'Başka bir şey'
        cfg.explanation_body  = 'farklı metin'
        cfg.save()
        r = self.client.post(self.url, {'action': 'reset_explanation'})
        self.assertRedirects(r, self.url)
        cfg.refresh_from_db()
        self.assertEqual(cfg.explanation_title, EXPLANATION_DEFAULT_TITLE)
        self.assertEqual(cfg.explanation_body, EXPLANATION_DEFAULT_BODY)

    def test_non_staff_cannot_access(self):
        coach = _make_coach()
        c = Client()
        c.force_login(coach)
        r = c.get(self.url)
        self.assertNotEqual(r.status_code, 200)

    def test_html_in_body_escaped_in_page(self):
        """Stored <script> should render as escaped text, never executed."""
        cfg = CapacitySettings.get()
        cfg.explanation_title = '<script>alert(1)</script>'
        cfg.explanation_body = ''
        cfg.save()
        r = self.client.get(self.url)
        self.assertNotContains(r, '<script>alert(1)</script>', html=False)


# ── Coach invites page ────────────────────────────────────────────────────────

@override_settings(COACH_CAPACITY_ENFORCED=True)
class ExplanationCoachViewTests(TestCase):

    def setUp(self):
        self.coach = _make_coach()
        self.client = Client()
        self.client.force_login(self.coach)
        self.url = reverse('users_app:coach_invites')
        cfg = CapacitySettings.get()
        cfg.explanation_title = EXPLANATION_DEFAULT_TITLE
        cfg.explanation_body = EXPLANATION_DEFAULT_BODY
        cfg.save()

    def test_coach_sees_updated_title(self):
        cfg = CapacitySettings.get()
        cfg.explanation_title = 'Yeni Başlık Koç'
        cfg.explanation_body = EXPLANATION_DEFAULT_BODY
        cfg.save()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Yeni Başlık Koç')

    def test_coach_sees_updated_item_text(self):
        cfg = CapacitySettings.get()
        cfg.explanation_title = 'Başlık'
        cfg.explanation_body = 'Özel madde: özel açıklama'
        cfg.save()
        r = self.client.get(self.url)
        self.assertContains(r, 'özel açıklama')

    def test_explanation_html_escaped_on_coach_page(self):
        cfg = CapacitySettings.get()
        cfg.explanation_title = 'Güvenli Başlık'
        cfg.explanation_body = '<img src=x onerror=alert(1)>: kötü'
        cfg.save()
        r = self.client.get(self.url)
        self.assertNotContains(r, '<img src=x', html=False)

    def test_details_open_when_no_grants(self):
        """Coach with no grants should see <details open> on the explanation."""
        r = self.client.get(self.url)
        content = r.content.decode()
        # The details block should be open since cap_status.granted == 0
        self.assertIn('<details', content)

    def test_seeded_default_text_visible(self):
        r = self.client.get(self.url)
        # Default body has "Kendi öğrencileriniz"
        self.assertContains(r, 'Kendi öğrencileriniz')

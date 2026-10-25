from django.test import Client, TestCase, override_settings


@override_settings(DEBUG=False)
class Custom404PageTests(TestCase):

    def setUp(self):
        self.client = Client(raise_request_exception=False)

    def test_404_status_code(self):
        resp = self.client.get('/non-existent-page-xyz/')
        self.assertEqual(resp.status_code, 404)

    def test_404_uses_custom_template(self):
        resp = self.client.get('/non-existent-page-xyz/')
        self.assertTemplateUsed(resp, '404.html')

    def test_404_contains_turkish_message(self):
        resp = self.client.get('/non-existent-page-xyz/')
        self.assertContains(resp, 'Aradığınız sayfa bulunamadı', status_code=404)

    def test_404_contains_login_url(self):
        resp = self.client.get('/non-existent-page-xyz/')
        self.assertContains(resp, '/auth/login/', status_code=404)

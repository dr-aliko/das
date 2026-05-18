import json
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from kocluk.models import AktiviteTipi, Ogrenci
from kocluk.services import tasks

User = get_user_model()


class OgrenciViewTests(TestCase):
    def setUp(self):
        self.koc_a = User.objects.create_user("koc_a", password="pw")
        self.koc_b = User.objects.create_user("koc_b", password="pw")
        self.client_a = Client()
        self.client_a.force_login(self.koc_a)
        self.client_b = Client()
        self.client_b.force_login(self.koc_b)

    def test_create_student(self):
        r = self.client_a.post(
            "/api/ogrenciler",
            data=json.dumps({"ad_soyad": "Ali"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertIn("id", r.json())

    def test_list_isolation(self):
        self.client_a.post(
            "/api/ogrenciler",
            data=json.dumps({"ad_soyad": "Ali"}),
            content_type="application/json",
        )
        r = self.client_b.get("/api/ogrenciler")
        self.assertEqual(r.json()["ogrenciler"], [])

    def test_delete_own_student(self):
        r = self.client_a.post(
            "/api/ogrenciler",
            data=json.dumps({"ad_soyad": "Ali"}),
            content_type="application/json",
        )
        ogr_id = r.json()["id"]
        r2 = self.client_a.delete(f"/api/ogrenciler/{ogr_id}")
        self.assertTrue(r2.json()["ok"])

    def test_delete_other_coach_student_blocked(self):
        r = self.client_a.post(
            "/api/ogrenciler",
            data=json.dumps({"ad_soyad": "Ali"}),
            content_type="application/json",
        )
        ogr_id = r.json()["id"]
        r2 = self.client_b.delete(f"/api/ogrenciler/{ogr_id}")
        self.assertEqual(r2.status_code, 404)

    def test_unauthenticated_redirected(self):
        r = Client().get("/api/ogrenciler")
        self.assertIn(r.status_code, [302, 403])


class GorevViewTests(TestCase):
    def setUp(self):
        self.koc_a = User.objects.create_user("koc_a", password="pw")
        self.koc_b = User.objects.create_user("koc_b", password="pw")
        self.ogr = Ogrenci.objects.create(koc=self.koc_a, ad_soyad="Ali")
        self.client_a = Client()
        self.client_a.force_login(self.koc_a)
        self.client_b = Client()
        self.client_b.force_login(self.koc_b)
        self.today = date.today().isoformat()

    def _create_task(self):
        payload = {
            "ogrenci_id": self.ogr.id,
            "tarih": self.today,
            "aktivite_tipi": AktiviteTipi.SORU_COZUMU,
            "ders_title": "TYT - Matematik",
            "ozel_sure_dk": 60,
            "detaylar": json.dumps([{"aciklama": "Sayfa 1", "sure_bilgisi": "30 dk"}]),
        }
        return self.client_a.post(
            "/api/gorevler",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_create_task(self):
        r = self._create_task()
        self.assertEqual(r.status_code, 201)

    def test_get_week(self):
        self._create_task()
        r = self.client_a.get(f"/api/gorevler?ogrenci_id={self.ogr.id}&hafta={self.today}")
        data = r.json()
        self.assertEqual(len(data["gorevler"]), 1)
        self.assertEqual(data["gorevler"][0]["detaylar"][0]["aciklama"], "Sayfa 1")

    def test_cross_coach_delete_blocked(self):
        r = self._create_task()
        task_id = r.json()["id"]
        r2 = self.client_b.delete(f"/api/gorev/{task_id}")
        self.assertEqual(r2.status_code, 404)

    def test_copy_to_date(self):
        r = self._create_task()
        task_id = r.json()["id"]
        from datetime import timedelta
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        r2 = self.client_a.post(
            f"/api/gorev/{task_id}/copy",
            data=json.dumps({"hedef_tarih": tomorrow}),
            content_type="application/json",
        )
        self.assertEqual(r2.status_code, 201)
        from kocluk.models import GorevGrubu
        self.assertEqual(GorevGrubu.objects.filter(ogrenci=self.ogr).count(), 2)

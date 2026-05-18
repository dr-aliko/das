from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from kocluk.models import AktiviteTipi, GorevGrubu, GrupDetay, Ogrenci
from kocluk.services import students, tasks
from kocluk.services import week as week_svc

User = get_user_model()


class WeekBoundsTests(TestCase):
    def test_monday_anchor(self):
        monday, sunday = week_svc.week_bounds(date(2024, 1, 17))  # Wednesday
        self.assertEqual(monday.weekday(), 0)
        self.assertEqual(sunday.weekday(), 6)
        self.assertEqual((sunday - monday).days, 6)

    def test_already_monday(self):
        monday, _ = week_svc.week_bounds(date(2024, 1, 15))
        self.assertEqual(monday, date(2024, 1, 15))

    def test_sunday_input(self):
        monday, _ = week_svc.week_bounds(date(2024, 1, 21))
        self.assertEqual(monday, date(2024, 1, 15))


class FormatMinutesTests(TestCase):
    def test_zero(self):
        self.assertEqual(week_svc.format_minutes(0), "Toplam: 0 dk")

    def test_less_than_hour(self):
        self.assertEqual(week_svc.format_minutes(45), "Toplam: 0s 45dk")

    def test_hours(self):
        self.assertEqual(week_svc.format_minutes(90), "Toplam: 1s 30dk")


class StudentServiceTests(TestCase):
    def setUp(self):
        self.koc_a = User.objects.create_user("koc_a", password="pw")
        self.koc_b = User.objects.create_user("koc_b", password="pw")

    def test_create_and_list(self):
        students.create(self.koc_a, "Ali Veli")
        result = students.list_for_koc(self.koc_a)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].ad_soyad, "Ali Veli")

    def test_coach_isolation(self):
        students.create(self.koc_a, "Ali Veli")
        self.assertEqual(students.list_for_koc(self.koc_b), [])

    def test_duplicate_same_coach(self):
        students.create(self.koc_a, "Ali Veli")
        result = students.create(self.koc_a, "Ali Veli")
        self.assertIsNone(result)

    def test_same_name_different_coach(self):
        students.create(self.koc_a, "Ali Veli")
        result = students.create(self.koc_b, "Ali Veli")
        self.assertIsNotNone(result)

    def test_delete_removes_only_own(self):
        a_ogr = students.create(self.koc_a, "Ali Veli")
        b_ogr = students.create(self.koc_b, "Ali Veli")
        students.delete(self.koc_a, a_ogr.id)
        self.assertEqual(students.list_for_koc(self.koc_a), [])
        self.assertEqual(len(students.list_for_koc(self.koc_b)), 1)


class TaskServiceTests(TestCase):
    def setUp(self):
        self.koc_a = User.objects.create_user("koc_a", password="pw")
        self.koc_b = User.objects.create_user("koc_b", password="pw")
        self.ogr = Ogrenci.objects.create(koc=self.koc_a, ad_soyad="Test Öğrenci")
        self.today = date.today()

    def _create_task(self, **kwargs):
        defaults = dict(
            tarih=self.today,
            ders_title="Mat",
            ozel_sure_dk=60,
            aktivite_tipi=AktiviteTipi.SORU_COZUMU,
            detaylar=[{"aciklama": "Sayfa 1-10", "sure_bilgisi": "30 dk"}],
        )
        defaults.update(kwargs)
        return tasks.create(self.koc_a, self.ogr.id, **defaults)

    def test_create_with_details(self):
        grup = self._create_task()
        self.assertIsNotNone(grup)
        self.assertEqual(GrupDetay.objects.filter(grup=grup).count(), 1)

    def test_sira_no_increments(self):
        g1 = self._create_task()
        g2 = self._create_task()
        self.assertEqual(g1.sira_no, 1)
        self.assertEqual(g2.sira_no, 2)

    def test_delete_cascades_details(self):
        grup = self._create_task()
        grup_id = grup.id
        tasks.delete(self.koc_a, grup_id)
        self.assertFalse(GorevGrubu.objects.filter(pk=grup_id).exists())
        self.assertFalse(GrupDetay.objects.filter(grup_id=grup_id).exists())

    def test_cross_coach_delete_blocked(self):
        grup = self._create_task()
        ok = tasks.delete(self.koc_b, grup.id)
        self.assertFalse(ok)
        self.assertTrue(GorevGrubu.objects.filter(pk=grup.id).exists())

    def test_copy_to_date(self):
        grup = self._create_task()
        tomorrow = self.today + timedelta(days=1)
        yeni = tasks.copy_to_date(self.koc_a, grup.id, tomorrow)
        self.assertIsNotNone(yeni)
        self.assertEqual(yeni.tarih, tomorrow)
        self.assertEqual(GorevGrubu.objects.filter(ogrenci=self.ogr).count(), 2)
        self.assertEqual(GrupDetay.objects.filter(grup=yeni).count(), 1)

    def test_swap_order(self):
        g1 = self._create_task()
        g2 = self._create_task()
        ok = tasks.swap_order(self.koc_a, g1.id, g2.id)
        self.assertTrue(ok)
        g1.refresh_from_db()
        g2.refresh_from_db()
        self.assertEqual(g1.sira_no, 2)
        self.assertEqual(g2.sira_no, 1)

    def test_swap_cross_day_blocked(self):
        g1 = self._create_task(tarih=self.today)
        g2 = self._create_task(tarih=self.today + timedelta(days=1))
        ok = tasks.swap_order(self.koc_a, g1.id, g2.id)
        self.assertFalse(ok)

    def test_week_fetch_no_n_plus_1(self):
        for _ in range(3):
            self._create_task()
        basi, sonu = week_svc.week_bounds(self.today)
        with self.assertNumQueries(2):  # 1 for groups + 1 prefetch for details
            results = tasks.week_for_student(self.koc_a, self.ogr.id, basi, sonu)
        self.assertEqual(len(results), 3)

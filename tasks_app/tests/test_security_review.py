import io
import json
from datetime import date

import pytest
from django.test import Client
from model_bakery import baker
from openpyxl import load_workbook

from tasks_app.forms import GorevForm
from tasks_app.models import GorevGrubu, GrupDetay, KaynakKitap, YouTubePlaylist, YouTubeVideo


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _own_student(coach):
    student = baker.make('users_app.User', role='student', is_active=True, coach=coach)
    baker.make('users_app.CoachStudent', coach=coach, student=student, active=True)
    return student


@pytest.mark.django_db
def test_non_object_json_body_is_rejected_not_crashed(coach_user, student_user):
    coach = _client(coach_user)
    student = _client(student_user)

    assert coach.post('/coach/tasks/api/gorevler', data='[1]', content_type='application/json').status_code == 400
    assert coach.post('/coach/tasks/api/gorev/1/copy', data='"x"', content_type='application/json').status_code == 400
    assert student.post('/student/tasks/api/gorev/new', data='[1]', content_type='application/json').status_code == 400
    assert student.post('/student/tasks/api/reset/', data='5', content_type='application/json').status_code == 400


def test_gorev_form_rejects_non_object_detay_items():
    form = GorevForm({
        'tarih': '2026-01-12', 'aktivite_tipi': 'tekrar', 'ders_title': 'Mat',
        'detaylar': json.dumps(['x', 5]),
    })

    assert not form.is_valid()


@pytest.mark.django_db
def test_kaynak_kitap_post_validates_input(coach_user):
    student = _own_student(coach_user)
    client = _client(coach_user)

    def post(**body):
        return client.post('/coach/tasks/api/kaynak-kitaplar', data=json.dumps(body), content_type='application/json')

    assert post(student_id='abc', kitap_adi='K', ders='Mat', sinav_tipi='TYT').status_code == 400
    assert post(student_id=student.id, kitap_adi=['K'], ders='Mat', sinav_tipi='TYT').status_code == 400
    assert post(student_id=student.id, kitap_adi='K' * 256, ders='Mat', sinav_tipi='TYT').status_code == 400
    assert post(student_id=student.id, kitap_adi='Kitap', ders='Mat', sinav_tipi='TYT').status_code == 201
    assert KaynakKitap.objects.filter(student=student, kitap_adi='Kitap').count() == 1


@pytest.mark.django_db
def test_coach_xlsx_export_keeps_formula_like_titles_as_text(coach_user):
    student = _own_student(coach_user)
    grup = baker.make(
        GorevGrubu, student=student, tarih=date(2026, 1, 12), ders_title='=HYPERLINK("http://x","y")',
        aktivite_tipi='tekrar', is_master=False, meta=None,
    )
    baker.make(GrupDetay, grup=grup, aciklama='detay')

    resp = _client(coach_user).get(f'/coach/tasks/export/hafta.xlsx?student_id={student.id}&hafta=2026-01-12')

    assert resp.status_code == 200
    cell = load_workbook(io.BytesIO(resp.content)).active.cell(row=2, column=1)
    assert cell.data_type == 's'
    assert cell.value.startswith('=HYPERLINK')


@pytest.mark.django_db
def test_student_xlsx_export_keeps_formula_like_titles_as_text(student_user):
    baker.make(
        GorevGrubu, student=student_user, tarih=date(2026, 1, 12), ders_title='=1+1',
        aktivite_tipi='tekrar', is_master=False, meta=None,
    )

    resp = _client(student_user).get('/student/tasks/export/hafta.xlsx?hafta=2026-01-12')

    assert resp.status_code == 200
    assert load_workbook(io.BytesIO(resp.content)).active.cell(row=2, column=1).data_type == 's'


@pytest.mark.django_db
def test_youtube_playlist_list_counts_videos_without_per_row_queries(coach_user, django_assert_max_num_queries):
    for index in range(3):
        playlist = baker.make(YouTubePlaylist, imported_by=coach_user, playlist_id=f'PL{index:010d}', subject=None)
        baker.make(YouTubeVideo, playlist=playlist, _quantity=index + 1)
    client = _client(coach_user)

    with django_assert_max_num_queries(6):
        resp = client.get('/coach/tasks/api/youtube/list')

    counts = sorted(p['video_count'] for p in resp.json()['playlists'])
    assert counts == [1, 2, 3]

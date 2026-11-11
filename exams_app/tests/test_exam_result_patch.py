import json
from datetime import date

import pytest
from django.test import Client
from model_bakery import baker

from exams_app.models import ExamResult


def _exam_with_results(student):
    exam = baker.make(
        'exams_app.Exam',
        student=student,
        publisher=baker.make('exams_app.Publisher'),
        exam_date=date(2026, 1, 10),
        custom_name='Deneme 1',
    )
    mat = baker.make('exams_app.Subject', name='TYT Matematik', exam_type='TYT', question_count=40)
    turkce = baker.make('exams_app.Subject', name='TYT Türkçe', exam_type='TYT', question_count=40)
    mat_result = baker.make(ExamResult, exam=exam, subject=mat,
                            correct_answers=10, wrong_answers=4, blank_answers=26)
    baker.make(ExamResult, exam=exam, subject=turkce,
               correct_answers=20, wrong_answers=0, blank_answers=20)
    return exam, mat_result


@pytest.mark.django_db
def test_result_patch_returns_new_subject_net_and_exam_total(student_user):
    exam, mat_result = _exam_with_results(student_user)
    client = Client()
    client.force_login(student_user)

    resp = client.patch(
        f'/student/exam/{exam.id}/result/{mat_result.id}/',
        data=json.dumps({'correct': 30, 'wrong': 8, 'blank': 2}),
        content_type='application/json',
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body['net_score'] == 28.0
    assert body['total_net'] == 48.0
    assert (body['correct'], body['wrong'], body['blank']) == (30, 8, 2)
    assert body['accuracy_percent'] == 75
    mat_result.refresh_from_db()
    assert mat_result.net_score == 28.0


@pytest.mark.django_db
def test_detail_page_binds_total_and_subject_counts_to_alpine_state(student_user):
    exam, mat_result = _exam_with_results(student_user)
    client = Client()
    client.force_login(student_user)

    html = client.get(f'/student/exam/{exam.id}/v2/?denemeler_v2=1').content.decode()

    assert 'x-text="fmtNet(displayNet, 2)"' in html
    assert f"x-text=\"subjectIndex['{mat_result.id}'].d\"" in html
    assert f"subjectIndex['{mat_result.id}'].acc" in html

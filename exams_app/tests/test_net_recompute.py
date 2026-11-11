from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client
from model_bakery import baker

from exams_app.models import BransDeneme, ExamResult


def _make_exam(student):
    return baker.make(
        'exams_app.Exam',
        student=student,
        publisher=baker.make('exams_app.Publisher'),
        exam_date=date(2026, 1, 10),
        custom_name='Deneme 1',
    )


@pytest.mark.django_db
def test_exam_edit_updates_stored_net_and_total(student_user):
    mat = baker.make('exams_app.Subject', name='TYT Matematik', exam_type='TYT')
    turkce = baker.make('exams_app.Subject', name='TYT Türkçe', exam_type='TYT')
    exam = _make_exam(student_user)
    baker.make(ExamResult, exam=exam, subject=mat, correct_answers=10, wrong_answers=4, blank_answers=26)
    baker.make(ExamResult, exam=exam, subject=turkce, correct_answers=20, wrong_answers=0, blank_answers=20)
    assert exam.total_net() == 29.0

    client = Client()
    client.force_login(student_user)
    resp = client.post(f'/student/exam/{exam.id}/edit/', {
        'publisher': exam.publisher_id,
        'custom_name': 'Deneme 1',
        'exam_date': '2026-01-10',
        f'correct_{mat.id}': 30, f'wrong_{mat.id}': 8, f'blank_{mat.id}': 2,
        f'correct_{turkce.id}': 20, f'wrong_{turkce.id}': 0, f'blank_{turkce.id}': 20,
        'errors_json': '[]',
    })

    assert resp.status_code == 302
    assert ExamResult.objects.get(exam=exam, subject=mat).net_score == 28.0
    exam.refresh_from_db()
    assert exam.total_net() == 48.0


@pytest.mark.django_db
def test_partial_saves_still_persist_net(student_user):
    subject = baker.make('exams_app.Subject', name='TYT Matematik', exam_type='TYT')
    result = baker.make(ExamResult, exam=_make_exam(student_user), subject=subject,
                        correct_answers=10, wrong_answers=0, blank_answers=0)
    ExamResult.objects.update_or_create(
        exam=result.exam, subject=subject,
        defaults={'correct_answers': 20, 'wrong_answers': 4},
    )
    result.refresh_from_db()
    assert result.net_score == 19.0

    entry = baker.make(BransDeneme, student=student_user, ders=subject,
                       tarih=date(2026, 1, 10), dogru=10, yanlis=0, bos=0)
    entry.dogru, entry.yanlis = 12, 8
    entry.save(update_fields=['dogru', 'yanlis'])
    entry.refresh_from_db()
    assert entry.net == 10.0


@pytest.mark.django_db
def test_rebuild_exam_nets_is_dry_by_default_and_fixes_on_apply(student_user):
    subject = baker.make('exams_app.Subject', name='TYT Matematik', exam_type='TYT')
    result = baker.make(ExamResult, exam=_make_exam(student_user), subject=subject,
                        correct_answers=30, wrong_answers=8, blank_answers=2)
    entry = baker.make(BransDeneme, student=student_user, ders=subject,
                       tarih=date(2026, 1, 10), dogru=12, yanlis=8, bos=0)
    ExamResult.objects.filter(pk=result.pk).update(net_score=9.0)
    BransDeneme.objects.filter(pk=entry.pk).update(net=1.0)

    out = StringIO()
    call_command('rebuild_exam_nets', stdout=out)
    result.refresh_from_db()
    entry.refresh_from_db()
    assert 'DRY RUN' in out.getvalue()
    assert (result.net_score, entry.net) == (9.0, 1.0)

    call_command('rebuild_exam_nets', '--apply', stdout=StringIO())
    result.refresh_from_db()
    entry.refresh_from_db()
    assert (result.net_score, entry.net) == (28.0, 10.0)

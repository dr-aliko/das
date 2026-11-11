import json
from datetime import date

import pytest
from django.test import Client
from model_bakery import baker

from exams_app.models import BransTopicError, ExamTopicError, StudentTask


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _foreign_task():
    other_coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    student = baker.make('users_app.User', role='student', is_active=True, coach=other_coach)
    baker.make('users_app.CoachStudent', coach=other_coach, student=student, active=True)
    return baker.make(StudentTask, student=student, topic=baker.make('exams_app.Topic'))


def _exam(student):
    return baker.make(
        'exams_app.Exam', student=student, publisher=baker.make('exams_app.Publisher'),
        exam_date=date(2026, 1, 10), custom_name='Deneme',
    )


@pytest.mark.django_db
def test_coach_cannot_complete_another_coachs_student_task(coach_user):
    task = _foreign_task()

    resp = _client(coach_user).post(f'/coach/task/{task.id}/complete/')

    assert resp.status_code == 403
    task.refresh_from_db()
    assert task.is_completed is False


@pytest.mark.django_db
def test_coach_cannot_delete_another_coachs_student_task(coach_user):
    task = _foreign_task()

    resp = _client(coach_user).post(
        f'/coach/task/{task.id}/action/',
        data=json.dumps({'action': 'cancel_assignment'}),
        content_type='application/json',
    )

    assert resp.status_code == 403
    assert StudentTask.objects.filter(id=task.id).exists()


@pytest.mark.django_db
def test_coach_can_still_complete_own_student_task(coach_user):
    student = baker.make('users_app.User', role='student', is_active=True, coach=coach_user)
    baker.make('users_app.CoachStudent', coach=coach_user, student=student, active=True)
    task = baker.make(StudentTask, student=student, topic=baker.make('exams_app.Topic'))

    resp = _client(coach_user).post(f'/coach/task/{task.id}/complete/')

    assert resp.status_code == 200
    task.refresh_from_db()
    assert task.is_completed is True


@pytest.mark.django_db
def test_step2_ignores_malformed_and_unknown_topic_rows(student_user):
    exam = _exam(student_user)
    topic = baker.make('exams_app.Topic')
    rows = [
        'not-a-dict',
        {'topicId': topic.id, 'wrongCount': 'abc'},
        {'topicId': 99999999, 'wrongCount': 2},
        {'topicId': topic.id, 'wrongCount': 3, 'blankCount': 1},
    ]

    resp = _client(student_user).post(
        f'/student/exam/{exam.id}/errors/', {'errors_json': json.dumps(rows)},
    )

    assert resp.status_code == 302
    saved = list(ExamTopicError.objects.filter(exam=exam).values_list('topic_id', 'wrong_count', 'blank_count'))
    assert saved == [(topic.id, 3, 1)]


@pytest.mark.django_db
def test_brans_topic_errors_ignores_malformed_rows(student_user):
    subject = baker.make('exams_app.Subject', name='TYT Matematik', exam_type='TYT', question_count=40)
    topic = baker.make('exams_app.Topic', subject=subject)
    entry = baker.make(
        'exams_app.BransDeneme', student=student_user, ders=subject,
        tarih=date(2026, 1, 10), dogru=10, yanlis=5, bos=0,
    )
    rows = ['x', {'topicId': [1], 'yanlisSayisi': 1}, {'topicId': topic.id, 'yanlisSayisi': 'abc'},
            {'topicId': topic.id, 'yanlisSayisi': 2}]

    resp = _client(student_user).post(
        f'/student/brans/{entry.pk}/konular/', {'errors_json': json.dumps(rows)},
    )

    assert resp.status_code == 302
    saved = list(BransTopicError.objects.filter(brans_deneme=entry).values_list('topic_id', 'yanlis_sayisi'))
    assert saved == [(topic.id, 2)]


@pytest.mark.django_db
@pytest.mark.parametrize('payload', ['[]', '{"question_id": "abc"}', '{"question_id": null}'])
def test_placement_save_answer_rejects_malformed_body(student_user, payload):
    attempt = baker.make('exams_app.StudentExamAttempt', student=student_user, is_completed=False)

    resp = _client(student_user).post(
        f'/student/seviye-tespiti/{attempt.pk}/cevap/', data=payload, content_type='application/json',
    )

    assert resp.status_code == 400

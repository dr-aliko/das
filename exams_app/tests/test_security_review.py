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


def _coach_page_query_count(coach, url, student_count):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    for _ in range(student_count):
        student = baker.make('users_app.User', role='student', is_active=True, coach=coach)
        baker.make('users_app.CoachStudent', coach=coach, student=student, active=True, source='coach')
        for correct in (5, 6, 7):
            exam = _exam(student)
            exam.exam_date = date.today()
            exam.save(update_fields=['exam_date'])
            baker.make('exams_app.ExamResult', exam=exam, correct_answers=correct, wrong_answers=0, blank_answers=0)
    client = _client(coach)
    with CaptureQueriesContext(connection) as ctx:
        assert client.get(url).status_code == 200
    return len(ctx)


@pytest.mark.django_db
@pytest.mark.parametrize('url', ['/coach/', '/coach/denemeler/'])
def test_coach_pages_query_count_does_not_grow_with_students(coach_user, url):
    few = _coach_page_query_count(coach_user, url, 2)
    many = _coach_page_query_count(coach_user, url, 5)

    assert many == few


@pytest.mark.django_db
def test_exam_overview_reports_total_and_latest_net(coach_user):
    student = baker.make('users_app.User', role='student', is_active=True, coach=coach_user)
    baker.make('users_app.CoachStudent', coach=coach_user, student=student, active=True)
    for exam_date, correct in ((date(2026, 1, 5), 10), (date(2026, 2, 5), 30)):
        exam = _exam(student)
        exam.exam_date = exam_date
        exam.save(update_fields=['exam_date'])
        baker.make('exams_app.ExamResult', exam=exam, correct_answers=correct, wrong_answers=0, blank_answers=0)

    row = _client(coach_user).get('/coach/denemeler/').context['student_data'][0]

    assert (row['total'], row['last_net'], row['last_date']) == (2, 30.0, date(2026, 2, 5))


@pytest.mark.django_db
def test_placement_rejects_answers_after_time_is_up(student_user):
    from datetime import timedelta
    from django.utils import timezone
    from exams_app.models import StudentExamAttempt, StudentQuestionAnswer

    placement = baker.make('exams_app.PlacementExam', is_active=True, duration_minutes=45)
    question = baker.make('exams_app.ExamQuestion', exam=placement)
    attempt = baker.make(StudentExamAttempt, student=student_user, exam=placement, is_completed=False)
    client = _client(student_user)
    answer_url = f'/student/seviye-tespiti/{attempt.pk}/cevap/'
    body = {'question_id': question.pk, 'selected_option': 'A', 'seconds': 5}

    in_time = client.post(answer_url, data=json.dumps(body), content_type='application/json')
    StudentExamAttempt.objects.filter(pk=attempt.pk).update(start_time=timezone.now() - timedelta(minutes=47))
    late_answer = client.post(
        answer_url, data=json.dumps({**body, 'selected_option': 'B'}), content_type='application/json',
    )
    late_time = client.post(
        f'/student/seviye-tespiti/{attempt.pk}/sure/', data=json.dumps(body), content_type='application/json',
    )
    submit = client.post(f'/student/seviye-tespiti/{attempt.pk}/bitir/')

    assert (in_time.status_code, late_answer.status_code, late_time.status_code) == (200, 403, 403)
    assert StudentQuestionAnswer.objects.get(attempt=attempt).selected_option == 'A'
    assert submit.status_code == 302


@pytest.mark.django_db
def test_placement_start_reuses_the_open_attempt(student_user):
    from exams_app.models import StudentExamAttempt

    placement = baker.make('exams_app.PlacementExam', is_active=True, duration_minutes=45)
    client = _client(student_user)

    first = client.post(f'/student/seviye-tespiti/{placement.pk}/baslat/')
    second = client.post(f'/student/seviye-tespiti/{placement.pk}/baslat/')

    assert first.url == second.url
    assert StudentExamAttempt.objects.filter(student=student_user, exam=placement).count() == 1

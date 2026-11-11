import json

import pytest
from django.test import Client
from model_bakery import baker

from konu_takip_app.models import StudentSubjectSrSetting, StudentTopicProgress


def _post(user, url, body):
    client = Client()
    client.force_login(user)
    return client.post(url, data=json.dumps(body), content_type='application/json')


@pytest.mark.django_db
def test_student_toggle_sr_unknown_subject_is_404(student_user):
    resp = _post(student_user, '/student/konu-takip/toggle-sr/', {'subject_id': 99999999})

    assert resp.status_code == 404
    assert not StudentSubjectSrSetting.objects.exists()


@pytest.mark.django_db
def test_coach_toggle_sr_unknown_subject_is_404(coach_user):
    student = baker.make('users_app.User', role='student', is_active=True, coach=coach_user)
    baker.make('users_app.CoachStudent', coach=coach_user, student=student, active=True)

    resp = _post(coach_user, '/coach/konu-takip/toggle-sr/', {'student_id': student.id, 'subject_id': 99999999})

    assert resp.status_code == 404
    assert not StudentSubjectSrSetting.objects.exists()


@pytest.mark.django_db
def test_toggle_sr_still_works_for_real_subject(student_user):
    subject = baker.make('exams_app.Subject', name='TYT Matematik', exam_type='TYT')

    resp = _post(student_user, '/student/konu-takip/toggle-sr/', {'subject_id': subject.id})

    assert resp.status_code == 200
    assert resp.json()['sr_enabled'] is True


@pytest.mark.django_db
def test_coach_cannot_touch_another_coachs_student(coach_user):
    other_coach = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    student = baker.make('users_app.User', role='student', is_active=True, coach=other_coach)
    baker.make('users_app.CoachStudent', coach=other_coach, student=student, active=True)
    subject = baker.make('exams_app.Subject', name='TYT Matematik', exam_type='TYT')
    topic = baker.make('konu_takip_app.KonuTakipTopic', subject=subject, checkable=True, parent=None)

    toggle = _post(coach_user, '/coach/konu-takip/toggle/', {
        'student_id': student.id, 'topic_id': topic.id, 'field': 'finished', 'value': True,
    })
    toggle_sr = _post(coach_user, '/coach/konu-takip/toggle-sr/', {'student_id': student.id, 'subject_id': subject.id})
    client = Client()
    client.force_login(coach_user)
    schedule = client.get(f'/coach/konu-takip/schedule/?student_id={student.id}')
    api = client.get(f'/coach/konu-takip/api/?student_id={student.id}')

    assert [toggle.status_code, toggle_sr.status_code, schedule.status_code, api.status_code] == [403] * 4
    assert not StudentTopicProgress.objects.exists()
    assert not StudentSubjectSrSetting.objects.exists()

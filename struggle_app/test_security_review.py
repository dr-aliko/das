import pytest
from django.test import Client
from django.utils import timezone
from model_bakery import baker

from struggle_app.models import StudentStruggleQuestion


@pytest.mark.django_db
def test_index_escapes_script_breakout_in_question_text(student_user):
    subject = baker.make('exams_app.Subject', name='TYT Matematik', exam_type='TYT')
    payload = '</script><script>alert(1)</script>'
    StudentStruggleQuestion.objects.create(
        student=student_user, subject=subject, question_text=payload, notes=payload,
        next_review_at=timezone.now(),
    )
    client = Client()
    client.force_login(student_user)

    html = client.get('/student/konu-takip/sorularim/').content.decode()

    assert payload not in html
    assert '\u003c/script\u003e' in html


def _add(client, **extra):
    subject = baker.make('exams_app.Subject', exam_type='TYT')
    return client.post('/student/konu-takip/sorularim/add/', {'subject_id': subject.id, 'question_text': 'soru', **extra})


@pytest.fixture
def student_client(student_user):
    from django.core.cache import cache
    cache.clear()
    client = Client()
    client.force_login(student_user)
    return client


@pytest.mark.django_db
def test_add_is_rate_limited_per_student(student_client, monkeypatch):
    monkeypatch.setattr('struggle_app.views._ADD_RATE', '2/h')

    statuses = [_add(student_client).status_code for _ in range(3)]

    assert statuses == [200, 200, 429]
    assert StudentStruggleQuestion.objects.count() == 2


@pytest.mark.django_db
def test_add_rejects_overlong_text_and_enforces_question_cap(student_client, monkeypatch):
    assert _add(student_client, question_text='x' * 5001).status_code == 400
    assert _add(student_client, notes='x' * 2001).status_code == 400

    monkeypatch.setattr('struggle_app.views._MAX_QUESTIONS', 1)
    assert _add(student_client).status_code == 200
    assert _add(student_client).status_code == 400
    assert StudentStruggleQuestion.objects.count() == 1

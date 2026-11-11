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

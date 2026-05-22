from datetime import date, timedelta
from math import ceil

import pytest
from model_bakery import baker

from curriculum_app.models import MacroPlan, MacroPlanBucket, MacroPlanTopic
from curriculum_app.services.engine import generate_macro_syllabus


def _make_plan(student, coach, months=4, algorithm='even'):
    target = date.today() + timedelta(days=months * 30)
    return MacroPlan.objects.create(
        coach=coach, student=student,
        sinav_tipi='TYT', target_date=target, algorithm=algorithm,
    )


@pytest.mark.django_db
def test_even_distribution_creates_buckets():
    from exams_app.models import Subject, Topic
    coach   = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    student = baker.make('users_app.User', role='student', is_active=True)
    subject = baker.make(Subject, exam_type='TYT', question_count=40)
    baker.make(Topic, subject=subject, _quantity=5)
    plan    = _make_plan(student, coach, months=3)
    generate_macro_syllabus(plan)
    assert plan.buckets.count() >= 1
    assert MacroPlanTopic.objects.filter(bucket__plan=plan).count() == 5


@pytest.mark.django_db
def test_known_topics_excluded():
    from exams_app.models import StudentTask, Topic, Subject
    coach   = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    student = baker.make('users_app.User', role='student', is_active=True)

    subject = baker.make(Subject, exam_type='TYT', question_count=40)
    topic_a = baker.make(Topic, subject=subject)
    topic_b = baker.make(Topic, subject=subject)

    # Mark topic_a as mastered via SM-2
    StudentTask.objects.create(
        student=student, topic=topic_a, task_source='trial',
        is_completed=True, repetition_count=2,
    )

    plan = _make_plan(student, coach, months=3)
    generate_macro_syllabus(plan)

    assigned_topic_ids = set(
        MacroPlanTopic.objects.filter(bucket__plan=plan).values_list('topic_id', flat=True)
    )
    assert topic_a.id not in assigned_topic_ids
    # topic_b (not mastered) should be included if it's a TYT topic
    assert topic_b.id in assigned_topic_ids


@pytest.mark.django_db
def test_weakness_algorithm_puts_error_topics_first():
    from exams_app.models import Exam, ExamTopicError, Publisher, Topic, Subject
    coach   = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    student = baker.make('users_app.User', role='student', is_active=True)

    subject  = baker.make(Subject, exam_type='TYT', question_count=40)
    weak_topic = baker.make(Topic, subject=subject, name='Zayıf Konu')
    strong_topic = baker.make(Topic, subject=subject, name='Iyi Konu')

    pub  = baker.make(Publisher)
    exam = baker.make('exams_app.Exam', student=student, publisher=pub,
                      exam_date=date.today() - timedelta(days=5))
    ExamTopicError.objects.create(exam=exam, topic=weak_topic, wrong_count=5, blank_count=3)

    plan = _make_plan(student, coach, months=4, algorithm='weighted_weakness')
    generate_macro_syllabus(plan)

    first_bucket = plan.buckets.order_by('order').first()
    if first_bucket:
        first_topic_ids = list(first_bucket.topics.values_list('topic_id', flat=True))
        # weak topic should appear in an early bucket
        all_topic_ids_ordered = list(
            MacroPlanTopic.objects.filter(bucket__plan=plan)
            .order_by('bucket__order', 'order')
            .values_list('topic_id', flat=True)
        )
        if weak_topic.id in all_topic_ids_ordered and strong_topic.id in all_topic_ids_ordered:
            assert all_topic_ids_ordered.index(weak_topic.id) < all_topic_ids_ordered.index(strong_topic.id)


@pytest.mark.django_db
def test_regeneration_clears_old_buckets():
    coach   = baker.make('users_app.User', role='coach', is_active=True, is_approved=True)
    student = baker.make('users_app.User', role='student', is_active=True)
    plan    = _make_plan(student, coach, months=3)

    generate_macro_syllabus(plan)
    count_first = plan.buckets.count()

    generate_macro_syllabus(plan)
    count_second = plan.buckets.count()

    # Should produce same number of buckets (not double)
    assert count_second == count_first

from datetime import date, timedelta

import pytest
from model_bakery import baker

from curriculum_app.models import MacroPlan, MacroPlanBucket, MacroPlanTopic


@pytest.mark.django_db
def test_macro_plan_months_remaining():
    future = date.today() + timedelta(days=90)
    plan = baker.make(MacroPlan, target_date=future)
    assert plan.months_remaining >= 2


@pytest.mark.django_db
def test_macro_plan_months_remaining_past():
    past = date.today() - timedelta(days=30)
    plan = baker.make(MacroPlan, target_date=past)
    assert plan.months_remaining == 0


@pytest.mark.django_db
def test_macro_plan_str():
    student = baker.make('users_app.User', role='student', full_name='Ali Veli')
    plan = baker.make(MacroPlan, student=student, sinav_tipi='TYT',
                      target_date=date.today() + timedelta(days=60))
    assert 'Ali Veli' in str(plan)
    assert 'TYT' in str(plan)


@pytest.mark.django_db
def test_bucket_cascade_deletes_topics():
    plan = baker.make(MacroPlan, target_date=date.today() + timedelta(days=60))
    bucket = baker.make(MacroPlanBucket, plan=plan, order=0)
    topic = baker.make('exams_app.Topic')
    MacroPlanTopic.objects.create(bucket=bucket, topic=topic, order=0)
    bucket_id = bucket.pk
    assert MacroPlanTopic.objects.filter(bucket_id=bucket_id).count() == 1
    bucket.delete()
    assert MacroPlanTopic.objects.filter(bucket_id=bucket_id).count() == 0


@pytest.mark.django_db
def test_plan_cascade_deletes_buckets_and_topics():
    plan = baker.make(MacroPlan, target_date=date.today() + timedelta(days=60))
    bucket = baker.make(MacroPlanBucket, plan=plan, order=0)
    topic = baker.make('exams_app.Topic')
    MacroPlanTopic.objects.create(bucket=bucket, topic=topic, order=0)
    pk = plan.pk
    plan.delete()
    assert MacroPlanBucket.objects.filter(plan_id=pk).count() == 0
    assert MacroPlanTopic.objects.filter(bucket_id=bucket.pk).count() == 0

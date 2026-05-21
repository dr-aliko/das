from datetime import date, timedelta
from math import ceil

import pytest
from model_bakery import baker

from exams_app.utils import apply_sm2


@pytest.fixture
def task(student_user):
    return baker.make(
        'exams_app.StudentTask',
        student=student_user,
        task_source='trial',
        repetition_count=0,
        easiness_factor=2.5,
        interval_days=0,
        next_review_date=None,
    )


@pytest.mark.django_db
def test_quality5_first_review(task):
    apply_sm2(task, quality=5)
    task.refresh_from_db()
    # rep_count=0 → interval becomes 1 day, count bumps to 1
    assert task.repetition_count == 1
    assert task.interval_days == 1
    assert task.next_review_date == date.today() + timedelta(days=1)
    # EF: 2.5 + 0.1 - 0*(0.08 + 0*0.02) = 2.6
    assert task.easiness_factor == pytest.approx(2.6, abs=0.01)


@pytest.mark.django_db
def test_quality4_second_review(task):
    task.repetition_count = 1
    task.interval_days = 1
    task.save(update_fields=['repetition_count', 'interval_days'])
    apply_sm2(task, quality=4)
    task.refresh_from_db()
    # rep_count=1 → interval becomes 6 days, count bumps to 2
    assert task.repetition_count == 2
    assert task.interval_days == 6
    assert task.next_review_date == date.today() + timedelta(days=6)


@pytest.mark.django_db
def test_quality3_third_review_uses_interval_formula(task):
    task.repetition_count = 2
    task.interval_days = 6
    task.easiness_factor = 2.5
    task.save(update_fields=['repetition_count', 'interval_days', 'easiness_factor'])
    apply_sm2(task, quality=3)
    task.refresh_from_db()
    # new_ef = 2.5 + 0.1 - 2*(0.08 + 2*0.02) = 2.6 - 0.24 = 2.36
    new_ef = round(2.5 + 0.1 - 2 * (0.08 + 2 * 0.02), 2)
    assert task.repetition_count == 3
    assert task.interval_days == ceil(6 * new_ef)
    assert task.next_review_date == date.today() + timedelta(days=task.interval_days)


@pytest.mark.django_db
def test_failure_branch_resets_task(task):
    task.repetition_count = 3
    task.interval_days = 15
    task.save(update_fields=['repetition_count', 'interval_days'])
    apply_sm2(task, quality=2)
    task.refresh_from_db()
    assert task.repetition_count == 0
    assert task.interval_days == 1
    assert task.next_review_date == date.today() + timedelta(days=1)


@pytest.mark.django_db
def test_easiness_factor_floor(student_user):
    # Repeated quality=3 reviews drive EF toward 1.3; it must never go below it.
    task = baker.make(
        'exams_app.StudentTask',
        student=student_user,
        task_source='branch',
        repetition_count=10,
        easiness_factor=1.31,
        interval_days=10,
    )
    apply_sm2(task, quality=3)
    task.refresh_from_db()
    assert task.easiness_factor >= 1.3

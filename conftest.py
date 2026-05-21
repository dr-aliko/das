import pytest
from model_bakery import baker


@pytest.fixture
def coach_user(db):
    return baker.make('users_app.User', role='coach', is_active=True, is_approved=True)


@pytest.fixture
def student_user(db):
    return baker.make('users_app.User', role='student', is_active=True)

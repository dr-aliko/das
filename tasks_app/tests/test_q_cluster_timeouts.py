import pytest
from django.conf import settings
from tasks_app.views import _YT_IMPORT_TIMEOUT


@pytest.mark.django_db
def test_q_cluster_retry_exceeds_all_task_timeouts():
    assert settings.Q_CLUSTER['retry'] > _YT_IMPORT_TIMEOUT, (
        f"Q_CLUSTER retry ({settings.Q_CLUSTER['retry']}s) must exceed the longest "
        f"per-task timeout (_YT_IMPORT_TIMEOUT={_YT_IMPORT_TIMEOUT}s) or Django-Q "
        f"will re-queue a still-running import and run it twice."
    )

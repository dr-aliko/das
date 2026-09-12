import json

from django.utils import timezone

from .models import KonuTakipTopic, StudentTopicProgress


def toggle_progress(student, topic_id, field, value):
    """
    Toggle a single progress field (started or finished) for a student.

    Invariants enforced:
      - finished=True  → started is also set to True
      - started=False  → finished is also cleared to False
    """
    progress, _ = StudentTopicProgress.objects.get_or_create(
        topic_id=topic_id,
        student=student,
        defaults={'started': False, 'finished': False},
    )

    now = timezone.now()

    if field == 'started':
        if value:
            progress.started = True
            if not progress.started_at:
                progress.started_at = now
        else:
            progress.started = False
            progress.finished = False
            progress.finished_at = None
    elif field == 'finished':
        if value:
            progress.finished = True
            if not progress.finished_at:
                progress.finished_at = now
            if not progress.started:
                progress.started = True
                if not progress.started_at:
                    progress.started_at = now
        else:
            progress.finished = False
            progress.finished_at = None

    progress.save()
    return progress


def build_topic_list(subject, student):
    """
    Return (topics_data, progress_json) for a given subject and student.

    topics_data is a list of dicts:
      {'type': 'leaf',   'topic': KonuTakipTopic}
      {'type': 'parent', 'topic': KonuTakipTopic,
       'children': [...], 'child_ids': [...], 'child_count': int}

    progress_json is a dict keyed by topic.id suitable for JSON serialisation.
    """
    all_topics = list(
        KonuTakipTopic.objects.filter(subject=subject).order_by('order')
    )

    topic_ids = [t.id for t in all_topics]
    progress_map = {
        p.topic_id: p
        for p in StudentTopicProgress.objects.filter(
            topic_id__in=topic_ids, student=student
        )
    }

    # Index children by parent_id for fast lookup
    children_by_parent: dict[int, list] = {}
    for t in all_topics:
        if t.parent_id is not None:
            children_by_parent.setdefault(t.parent_id, []).append(t)

    progress_json: dict = {}
    topics_data: list = []

    for topic in all_topics:
        if topic.parent_id is not None:
            continue  # handled under parent

        if not topic.checkable:
            # Category header — not toggleable; only its children go in progress_json.
            children = sorted(
                children_by_parent.get(topic.id, []), key=lambda t: t.order
            )
            child_ids = [c.id for c in children]
            for c in children:
                cp = progress_map.get(c.id)
                progress_json[c.id] = {
                    'started': cp.started if cp else False,
                    'finished': cp.finished if cp else False,
                }
            topics_data.append({
                'type': 'parent',
                'topic': topic,
                'children': children,
                'child_ids': child_ids,
                'child_count': len(children),
            })
        else:
            # Leaf topic — directly checkable.
            p = progress_map.get(topic.id)
            progress_json[topic.id] = {
                'started': p.started if p else False,
                'finished': p.finished if p else False,
            }
            topics_data.append({'type': 'leaf', 'topic': topic})

    return topics_data, progress_json

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


def _gather_leaf_ids(nodes):
    """Recursively collect all leaf topic IDs from a list of node dicts."""
    ids = []
    for node in nodes:
        if node['type'] == 'leaf':
            ids.append(node['topic'].id)
        else:
            ids.extend(_gather_leaf_ids(node['children']))
    return ids


def _build_node(topic, children_by_parent, progress_map, progress_json):
    """
    Recursively build a node dict for `topic`.
    Leaf topics (checkable=True) are inserted into progress_json.
    Returns {'type': 'leaf'/'parent', 'topic': ..., ...}
    """
    if topic.checkable:
        cp = progress_map.get(topic.id)
        progress_json[topic.id] = {
            'started': cp.started if cp else False,
            'finished': cp.finished if cp else False,
        }
        return {'type': 'leaf', 'topic': topic}

    # Non-checkable category header — recurse into children.
    direct_children = sorted(
        children_by_parent.get(topic.id, []), key=lambda t: t.order
    )
    child_nodes = [
        _build_node(c, children_by_parent, progress_map, progress_json)
        for c in direct_children
    ]
    leaf_ids = _gather_leaf_ids(child_nodes)
    return {
        'type': 'parent',
        'topic': topic,
        'children': child_nodes,
        'child_ids': leaf_ids,
        'child_count': len(leaf_ids),
    }


def build_flat_topics(topics_data):
    """
    Flatten the nested topics_data tree into a list of row dicts for Alpine x-for rendering.

    row_type values (drive CSS classes client-side):
      'header_1'  — level-1 category header (Sınıf level)
      'header_2'  — level-2 sub-category header (▸ prefix)
      'leaf_1'    — checkable leaf under a level-1 header (pl-7 + └)
      'leaf_2'    — checkable leaf under a level-2 header (pl-14 + └)
      'root_leaf' — checkable leaf at root level (no indent)
    """
    rows = []
    for item in topics_data:
        if item['type'] == 'leaf':
            rows.append({'row_type': 'root_leaf', 'id': item['topic'].id, 'name': item['topic'].name})
        else:
            rows.append({
                'row_type': 'header_1',
                'id': item['topic'].id,
                'name': item['topic'].name,
                'child_ids': item['child_ids'],
                'child_count': item['child_count'],
            })
            for child in item['children']:
                if child['type'] == 'leaf':
                    rows.append({'row_type': 'leaf_1', 'id': child['topic'].id, 'name': child['topic'].name})
                else:
                    rows.append({
                        'row_type': 'header_2',
                        'id': child['topic'].id,
                        'name': child['topic'].name,
                        'child_ids': child['child_ids'],
                        'child_count': child['child_count'],
                    })
                    for grandchild in child['children']:
                        rows.append({'row_type': 'leaf_2', 'id': grandchild['topic'].id, 'name': grandchild['topic'].name})
    return rows


def build_topic_list(subject, student):
    """
    Return (topics_data, progress_json) for a given subject and student.

    topics_data is a list of node dicts at the root level:
      {'type': 'leaf',   'topic': KonuTakipTopic}
      {'type': 'parent', 'topic': KonuTakipTopic,
       'children': [node, ...],   # may contain both leaf and parent nodes
       'child_ids': [int, ...],   # ALL leaf descendant IDs at any depth
       'child_count': int}

    progress_json is a dict keyed by topic.id (only checkable leaves).
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

    children_by_parent: dict = {}
    for t in all_topics:
        if t.parent_id is not None:
            children_by_parent.setdefault(t.parent_id, []).append(t)

    progress_json: dict = {}
    topics_data: list = []

    for topic in all_topics:
        if topic.parent_id is not None:
            continue  # handled recursively under parent
        topics_data.append(
            _build_node(topic, children_by_parent, progress_map, progress_json)
        )

    return topics_data, progress_json

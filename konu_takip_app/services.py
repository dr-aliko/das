from datetime import timedelta

from django.utils import timezone

from .models import KonuTakipTopic, StudentSubjectSrSetting, StudentTopicProgress
from .sr_utils import VALID_QUALITIES, apply_sm2


def _compute_review(progress, quality):
    """Apply SM2-inspired interval. Mutates progress but does NOT save."""
    new_interval, new_ease = apply_sm2(
        progress.review_count,
        progress.current_interval_days,
        progress.ease_factor,
        quality,
    )
    now = timezone.now()
    progress.current_interval_days = new_interval
    progress.ease_factor = new_ease
    progress.next_review_at = now + timedelta(days=new_interval)
    progress.last_reviewed_at = now
    progress.review_count += 1


def toggle_progress(student, topic_id, field, value, quality=None):
    """
    Toggle a single progress field (started or finished) for a student.

    Invariants enforced:
      - finished=True  → started is also set to True
      - started=False  → finished is also cleared to False
    When field='finished' and value=True and quality is provided, the SM2 review
    schedule is computed and stored.
    """
    progress, _ = StudentTopicProgress.objects.get_or_create(
        topic_id=topic_id,
        student=student,
        defaults={
            'started': False,
            'finished': False,
            'current_interval_days': 1,
            'ease_factor': 2.5,
            'review_count': 0,
            'next_review_at': None,
            'last_reviewed_at': None,
        },
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
            progress.next_review_at = None
    elif field == 'finished':
        if value:
            progress.finished = True
            if not progress.finished_at:
                progress.finished_at = now
            if not progress.started:
                progress.started = True
                if not progress.started_at:
                    progress.started_at = now
            if quality in VALID_QUALITIES:
                _compute_review(progress, quality)
        else:
            progress.finished = False
            progress.finished_at = None
            progress.next_review_at = None  # clear pending review; keep review_count

    progress.save()
    return progress


def submit_review(student, topic_id, quality):
    """Submit a quality rating from the 'Tekrar Zamanı Gelenler' section."""
    if quality not in VALID_QUALITIES:
        return None
    progress = StudentTopicProgress.objects.filter(
        topic_id=topic_id, student=student, finished=True
    ).first()
    if not progress:
        return None
    _compute_review(progress, quality)
    progress.save()
    return progress


def get_subject_sr_settings(student):
    """Return {subject_id: sr_enabled} for all explicitly-stored settings. Absence means False."""
    if not student:
        return {}
    return {
        row.subject_id: row.sr_enabled
        for row in StudentSubjectSrSetting.objects.filter(student=student)
    }


def toggle_subject_sr(student, subject_id):
    """Flip sr_enabled for a (student, subject) pair. Returns the new value.

    No row (never touched) resolves to False (opt-in default), so the first
    toggle creates a row and sets it to True (turning SR on).
    """
    setting, _ = StudentSubjectSrSetting.objects.get_or_create(
        student=student,
        subject_id=subject_id,
        defaults={'sr_enabled': False},
    )
    setting.sr_enabled = not setting.sr_enabled
    setting.save(update_fields=['sr_enabled'])
    return setting.sr_enabled


def get_all_reviews_json(student):
    """All topics in an active review cycle sorted soonest-first.
    Topics whose subject has SR disabled (or not explicitly enabled) are excluded."""
    if not student:
        return []
    sr_settings = get_subject_sr_settings(student)
    now = timezone.now()
    qs = (
        StudentTopicProgress.objects.filter(
            student=student,
            finished=True,
            review_count__gte=1,
            next_review_at__isnull=False,
        )
        .select_related('topic__subject')
        .order_by('next_review_at')
    )
    result = []
    for p in qs:
        subject_id = p.topic.subject_id if p.topic.subject else None
        if not sr_settings.get(subject_id, False):
            continue
        result.append({
            'topic_id': p.topic_id,
            'topic_name': p.topic.name,
            'subject_name': p.topic.subject.name if p.topic.subject else '',
            'subject_id': subject_id,
            'next_review_at': p.next_review_at.isoformat(),
            'is_due': p.next_review_at <= now,
            'review_count': p.review_count,
        })
    return result


def get_due_reviews_json(student):
    """Return serialized list of topics due for review, sorted soonest-first."""
    now = timezone.now()
    qs = (
        StudentTopicProgress.objects.filter(
            student=student,
            finished=True,
            next_review_at__lte=now,
        )
        .select_related('topic__subject')
        .order_by('next_review_at')
    )
    result = []
    for p in qs:
        result.append({
            'topic_id': p.topic_id,
            'topic_name': p.topic.name,
            'subject_name': p.topic.subject.name if p.topic.subject else '',
            'next_review_at': p.next_review_at.isoformat(),
            'is_overdue': p.next_review_at <= now,
            'review_count': p.review_count,
        })
    return result


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
            'next_review_at': cp.next_review_at.isoformat() if cp and cp.next_review_at else None,
            'review_count': cp.review_count if cp else 0,
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

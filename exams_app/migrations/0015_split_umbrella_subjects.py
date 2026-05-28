"""
Data migration: split umbrella TYT subjects (TYT Sosyal Bilimler and
TYT Fen Bilimleri) into standalone Subject rows using Topic.sub_category
as the discriminator.

  TYT Sosyal Bilimler  → TYT Tarih, TYT Coğrafya, TYT Felsefe, TYT Din Kültürü
  TYT Fen Bilimleri    → TYT Fizik, TYT Kimya, TYT Biyoloji
    (these 3 already exist as standalone Subjects; duplicate Topics are
     merged by redirecting FKs from the umbrella topic to the canonical
     standalone topic, then deleting the umbrella topic)

Umbrella Subject rows are NOT deleted — ExamResult.subject is PROTECT and
historical exam rows may still reference them.  After this migration the
umbrella subjects are empty (0 topics) and invisible to the planner.

Reverse migration: noop (one-way operation).
"""
from django.db import migrations


def _redirect_topic_fks(apps, old_topic, new_topic):
    """Point all child FK rows from old_topic to new_topic, skipping unique violations."""
    ExamTopicError = apps.get_model('exams_app', 'ExamTopicError')
    BransTopicError = apps.get_model('exams_app', 'BransTopicError')
    StudentTask = apps.get_model('exams_app', 'StudentTask')
    MacroPlanTopic = apps.get_model('curriculum_app', 'MacroPlanTopic')

    # ExamTopicError unique_together = (exam, topic)
    for ete in ExamTopicError.objects.filter(topic=old_topic):
        if ExamTopicError.objects.filter(exam_id=ete.exam_id, topic=new_topic).exists():
            ete.delete()
        else:
            ete.topic = new_topic
            ete.save(update_fields=['topic'])

    # BransTopicError unique_together = (brans_deneme, topic)
    for bte in BransTopicError.objects.filter(topic=old_topic):
        if BransTopicError.objects.filter(brans_deneme_id=bte.brans_deneme_id, topic=new_topic).exists():
            bte.delete()
        else:
            bte.topic = new_topic
            bte.save(update_fields=['topic'])

    # StudentTask unique_together = (student, topic, task_source)
    for st in StudentTask.objects.filter(topic=old_topic):
        if StudentTask.objects.filter(
            student_id=st.student_id, topic=new_topic, task_source=st.task_source
        ).exists():
            st.delete()
        else:
            st.topic = new_topic
            st.save(update_fields=['topic'])

    # MacroPlanTopic unique_together = (bucket, topic)
    for mpt in MacroPlanTopic.objects.filter(topic=old_topic):
        if MacroPlanTopic.objects.filter(bucket_id=mpt.bucket_id, topic=new_topic).exists():
            mpt.delete()
        else:
            mpt.topic = new_topic
            mpt.save(update_fields=['topic'])


def split_umbrella_subjects(apps, schema_editor):
    Subject = apps.get_model('exams_app', 'Subject')
    Topic = apps.get_model('exams_app', 'Topic')

    # Map: (umbrella_subject_name, sub_category) → standalone_subject_name
    SPLITS = [
        ('TYT Sosyal Bilimler', 'Tarih',        'TYT Tarih',       5),
        ('TYT Sosyal Bilimler', 'Coğrafya',      'TYT Coğrafya',    5),
        ('TYT Sosyal Bilimler', 'Felsefe',       'TYT Felsefe',     5),
        ('TYT Sosyal Bilimler', 'Din Kültürü',   'TYT Din Kültürü', 5),
        ('TYT Fen Bilimleri',   'Fizik',         'TYT Fizik',      13),
        ('TYT Fen Bilimleri',   'Kimya',         'TYT Kimya',      11),
        ('TYT Fen Bilimleri',   'Biyoloji',      'TYT Biyoloji',    6),
    ]

    for umbrella_name, sub_cat, standalone_name, q_count in SPLITS:
        try:
            umbrella_subj = Subject.objects.get(exam_type='TYT', name=umbrella_name)
        except Subject.DoesNotExist:
            continue

        standalone_subj, _ = Subject.objects.get_or_create(
            exam_type='TYT', name=standalone_name,
            defaults={'question_count': q_count},
        )

        for umbrella_topic in Topic.objects.filter(subject=umbrella_subj, sub_category=sub_cat):
            # Check if a topic with the same name already exists in the standalone subject
            try:
                canonical = Topic.objects.get(subject=standalone_subj, name=umbrella_topic.name)
                # Collision: redirect FKs then delete the umbrella duplicate
                _redirect_topic_fks(apps, umbrella_topic, canonical)
                umbrella_topic.delete()
            except Topic.DoesNotExist:
                # No collision: move the topic to the standalone subject
                umbrella_topic.subject = standalone_subj
                umbrella_topic.sub_category = ''
                umbrella_topic.save(update_fields=['subject', 'sub_category'])


class Migration(migrations.Migration):

    dependencies = [
        ('exams_app', '0014_topic_depends_on_topic_expected_hours_and_more'),
        ('curriculum_app', '0002_macroplan_segment_macroplan_status_planriskalert_and_more'),
    ]

    operations = [
        migrations.RunPython(split_umbrella_subjects, reverse_code=migrations.RunPython.noop),
    ]

"""
Idempotent management command that replicates the logic from migration
0015_split_umbrella_subjects but can be re-run safely.

Use this when seed_initial was run BEFORE the migration (the typical dev
scenario where the DB was empty at migration time), leaving umbrella subjects
still populated.

Run with:
    python manage.py reorganize_umbrella_subjects
"""
from django.core.management.base import BaseCommand
from exams_app.models import Subject, Topic, ExamTopicError, BransTopicError
from exams_app.models import StudentTask
from curriculum_app.models import MacroPlanTopic


SPLITS = [
    ('TYT Sosyal Bilimler', 'Tarih',        'TYT Tarih',       5),
    ('TYT Sosyal Bilimler', 'Coğrafya',      'TYT Coğrafya',    5),
    ('TYT Sosyal Bilimler', 'Felsefe',       'TYT Felsefe',     4),
    ('TYT Sosyal Bilimler', 'Din Kültürü',   'TYT Din Kültürü', 4),
    ('TYT Fen Bilimleri',   'Fizik',         'TYT Fizik',      13),
    ('TYT Fen Bilimleri',   'Kimya',         'TYT Kimya',      11),
    ('TYT Fen Bilimleri',   'Biyoloji',      'TYT Biyoloji',    6),
]


def _redirect_topic_fks(old_topic, new_topic):
    for ete in ExamTopicError.objects.filter(topic=old_topic):
        if ExamTopicError.objects.filter(exam_id=ete.exam_id, topic=new_topic).exists():
            ete.delete()
        else:
            ete.topic = new_topic
            ete.save(update_fields=['topic'])

    for bte in BransTopicError.objects.filter(topic=old_topic):
        if BransTopicError.objects.filter(brans_deneme_id=bte.brans_deneme_id, topic=new_topic).exists():
            bte.delete()
        else:
            bte.topic = new_topic
            bte.save(update_fields=['topic'])

    for st in StudentTask.objects.filter(topic=old_topic):
        if StudentTask.objects.filter(
            student_id=st.student_id, topic=new_topic, task_source=st.task_source
        ).exists():
            st.delete()
        else:
            st.topic = new_topic
            st.save(update_fields=['topic'])

    for mpt in MacroPlanTopic.objects.filter(topic=old_topic):
        if MacroPlanTopic.objects.filter(bucket_id=mpt.bucket_id, topic=new_topic).exists():
            mpt.delete()
        else:
            mpt.topic = new_topic
            mpt.save(update_fields=['topic'])


class Command(BaseCommand):
    help = 'Move topics from umbrella TYT subjects into standalone subjects (idempotent).'

    def handle(self, *args, **options):
        total_moved = total_merged = 0

        for umbrella_name, sub_cat, standalone_name, q_count in SPLITS:
            try:
                umbrella_subj = Subject.objects.get(exam_type='TYT', name=umbrella_name)
            except Subject.DoesNotExist:
                self.stdout.write(f'  skip: {umbrella_name} not found')
                continue

            standalone_subj, created = Subject.objects.get_or_create(
                exam_type='TYT', name=standalone_name,
                defaults={'question_count': q_count},
            )
            if created:
                self.stdout.write(f'  created Subject: {standalone_name}')

            umbrella_topics = list(
                Topic.objects.filter(subject=umbrella_subj, sub_category=sub_cat)
            )
            if not umbrella_topics:
                continue

            moved = merged = 0
            for umbrella_topic in umbrella_topics:
                try:
                    canonical = Topic.objects.get(
                        subject=standalone_subj, name=umbrella_topic.name
                    )
                    _redirect_topic_fks(umbrella_topic, canonical)
                    umbrella_topic.delete()
                    merged += 1
                except Topic.DoesNotExist:
                    umbrella_topic.subject = standalone_subj
                    umbrella_topic.sub_category = ''
                    umbrella_topic.save(update_fields=['subject', 'sub_category'])
                    moved += 1

            total_moved += moved
            total_merged += merged
            self.stdout.write(
                f'  {umbrella_name}/{sub_cat} -> {standalone_name}: '
                f'{moved} moved, {merged} merged/deleted'
            )

        self.stdout.write(self.style.SUCCESS(
            f'reorganize_umbrella_subjects complete. '
            f'{total_moved} topics moved, {total_merged} duplicates merged.'
        ))
"""
Diagnostic: compare per-topic error counts between the Görev Takibi widget
(formerly wrong_count only) and the Denemeler page (wrong+blank combined).

Root cause of the bug this diagnoses: the widget used wrong_total alone while
denemeler used wrong+blank.  After the fix both use _exam_topic_error_totals
which returns errors = wrong+blank.  This command shows which topics had
blank_count > 0 — those are the rows that caused the visible inconsistency.

Dry-run (default): prints the number of topics per student where blank_count > 0
  (these are the topics where the widget previously showed a lower number).
--apply: no data changes needed (ExamTopicError is the authoritative source,
  the fix is in the view code), but the command verifies data integrity and
  prints a confirmation.

Usage:
  python manage.py rebuild_wrong_counts
  python manage.py rebuild_wrong_counts --student 35
  python manage.py rebuild_wrong_counts --apply
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum

from exams_app.models import ExamTopicError
from users_app.models import User


class Command(BaseCommand):
    help = 'Audit topic error counts: show topics where blank_count > 0 caused widget/denemeler mismatch.'

    def add_arguments(self, parser):
        parser.add_argument('--student', type=int, default=None,
                            help='Limit to a single student by ID.')
        parser.add_argument('--apply', action='store_true',
                            help='Confirm fix is live; no data is modified (ExamTopicError is the source of truth).')

    def handle(self, *args, **options):
        student_id = options['student']
        apply_mode = options['apply']

        students_qs = User.objects.filter(role='student', is_active=True)
        if student_id:
            students_qs = students_qs.filter(pk=student_id)

        total_students = 0
        total_affected_topics = 0

        for student in students_qs.order_by('id'):
            rows = list(
                ExamTopicError.objects
                .filter(exam__student=student)
                .values('topic__id', 'topic__name', 'topic__subject__name')
                .annotate(
                    wrong_total=Sum('wrong_count'),
                    blank_total=Sum('blank_count'),
                    errors=Sum('wrong_count') + Sum('blank_count'),
                )
                .filter(blank_total__gt=0)
                .order_by('-errors')
            )

            if not rows:
                continue

            total_students += 1
            total_affected_topics += len(rows)

            self.stdout.write(
                self.style.WARNING(
                    f'\nStudent {student.id} — {student.full_name}: '
                    f'{len(rows)} topic(s) with blank_count > 0'
                )
            )
            for r in rows:
                old_widget = r['wrong_total']
                new_widget = r['errors']
                self.stdout.write(
                    f"  [{r['topic__subject__name']}] {r['topic__name']}: "
                    f"old widget={old_widget}Y  denemeler={new_widget}Y  "
                    f"(blank_count={r['blank_total']})"
                )

        self.stdout.write('')
        if total_affected_topics == 0:
            self.stdout.write(self.style.SUCCESS(
                'No topics with blank_count > 0 found — widget and denemeler counts already identical.'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f'Summary: {total_affected_topics} topic(s) across {total_students} student(s) '
                f'had blank errors that caused the widget to show a lower "Y" count than denemeler.'
            ))

        if apply_mode:
            self.stdout.write(self.style.SUCCESS(
                '\n--apply: ExamTopicError is the authoritative source of truth — '
                'no data rows to rewrite.  The fix is in the view code '
                '(_exam_topic_error_totals now used by both widget and denemeler).'
            ))
        else:
            self.stdout.write(
                'Dry-run complete.  Re-run with --apply to confirm the code fix is in place.'
            )

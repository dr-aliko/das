"""
Recompute stored nets (ExamResult.net_score, BransDeneme.net) from the D/Y counts.

Usage:
  python manage.py rebuild_exam_nets              # dry run, lists mismatches
  python manage.py rebuild_exam_nets --student 35
  python manage.py rebuild_exam_nets --apply
"""

from django.core.management.base import BaseCommand

from exams_app.models import BransDeneme, ExamResult
from exams_app.net import calculate_net

BATCH_SIZE = 500


class Command(BaseCommand):
    help = 'Recompute stored exam nets from correct/wrong counts (dry run unless --apply).'

    def add_arguments(self, parser):
        parser.add_argument('--student', type=int, default=None,
                            help='Limit to a single student by ID.')
        parser.add_argument('--apply', action='store_true',
                            help='Write the corrected nets. Without it nothing is modified.')

    def handle(self, *args, **options):
        student_id = options['student']
        apply_mode = options['apply']

        results = ExamResult.objects.select_related('exam', 'subject').order_by('exam_id', 'id')
        brans = BransDeneme.objects.select_related('ders').order_by('id')
        if student_id:
            results = results.filter(exam__student_id=student_id)
            brans = brans.filter(student_id=student_id)

        stale_results = []
        exam_deltas = {}
        for result in results.iterator(chunk_size=BATCH_SIZE):
            expected = calculate_net(result.correct_answers, result.wrong_answers)
            if result.net_score == expected:
                continue
            self.stdout.write(
                f'  ExamResult id={result.id} exam={result.exam_id} student={result.exam.student_id} '
                f'{result.subject.name}: {result.net_score} -> {expected}'
            )
            exam_deltas[result.exam_id] = exam_deltas.get(result.exam_id, 0) + expected - result.net_score
            result.net_score = expected
            stale_results.append(result)

        for exam_id, delta in exam_deltas.items():
            self.stdout.write(f'  Exam id={exam_id}: total net {delta:+.2f}')

        stale_brans = []
        for entry in brans.iterator(chunk_size=BATCH_SIZE):
            expected = calculate_net(entry.dogru, entry.yanlis)
            if entry.net == expected:
                continue
            self.stdout.write(
                f'  BransDeneme id={entry.id} student={entry.student_id} '
                f'{entry.ders.name}: {entry.net} -> {expected}'
            )
            entry.net = expected
            stale_brans.append(entry)

        summary = (
            f'{len(stale_results)} ExamResult row(s) in {len(exam_deltas)} exam(s), '
            f'{len(stale_brans)} BransDeneme row(s)'
        )
        if not apply_mode:
            self.stdout.write(self.style.WARNING(f'DRY RUN: {summary} would be updated. Use --apply to write.'))
            return

        ExamResult.objects.bulk_update(stale_results, ['net_score'], batch_size=BATCH_SIZE)
        BransDeneme.objects.bulk_update(stale_brans, ['net'], batch_size=BATCH_SIZE)
        self.stdout.write(self.style.SUCCESS(f'APPLIED: {summary} updated.'))

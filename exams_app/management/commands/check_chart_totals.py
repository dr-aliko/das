"""
Read-only diagnostic: compare each exam's chart total (as _build_student_chart_data
would compute it post-fix) against Exam.total_net().

A discrepancy means:
  - DIFF_TYT : split-subject grouping bug still present (should not happen after fix)
  - DIFF_AYT : exam contains AYT result rows; chart only shows TYT — not a code bug,
               but worth knowing so total_net() isn't shown as the chart label on AYT exams
  - DIFF_OTHER: unexpected subject names not in any known group

Usage:
  python manage.py check_chart_totals
  python manage.py check_chart_totals --student 42
  python manage.py check_chart_totals --show-ok
"""

from django.core.management.base import BaseCommand

from exams_app.models import Exam
from exams_app.views import _FEN_NAMES, _SOSYAL_NAMES, _TYT_DISPLAY_SUBJECTS

_ALL_SOSYAL = _SOSYAL_NAMES | {'TYT Sosyal Bilimler'}

_KNOWN_TYT = _FEN_NAMES | _ALL_SOSYAL | {'TYT Türkçe', 'TYT Matematik'}
_KNOWN_AYT = frozenset({
    'AYT Matematik', 'AYT Türk Dili', 'AYT Edebiyat',
    'AYT Tarih 1', 'AYT Tarih 2', 'AYT Tarih',
    'AYT Coğrafya 1', 'AYT Coğrafya 2', 'AYT Coğrafya',
    'AYT Felsefe Grubu', 'AYT Felsefe',
    'AYT Din Kültürü',
    'AYT Fizik', 'AYT Kimya', 'AYT Biyoloji',
    'AYT Matematik (Sayısal)', 'AYT Matematik (EA)',
})


def _chart_total(results):
    """Replicates the post-fix _build_student_chart_data aggregation for one exam."""
    rm = {r.subject.name: r.net_score for r in results}
    rm['TYT Fen Bilimleri']   = sum(rm.get(s, 0) for s in _FEN_NAMES)
    rm['TYT Sosyal Bilimler'] = sum(rm.get(s, 0) for s in _ALL_SOSYAL)
    return round(sum(rm.get(n, 0) for n in _TYT_DISPLAY_SUBJECTS), 2)


class Command(BaseCommand):
    help = 'Read-only: list exams where chart total differs from Exam.total_net()'

    def add_arguments(self, parser):
        parser.add_argument('--student', type=int, metavar='USER_ID',
                            help='Limit to a specific student user id')
        parser.add_argument('--show-ok', action='store_true',
                            help='Also print exams where totals match')

    def handle(self, *args, **options):
        qs = Exam.objects.prefetch_related('results__subject').select_related('student')
        if options['student']:
            qs = qs.filter(student_id=options['student'])
        qs = qs.order_by('student__full_name', 'exam_date', 'id')

        total = ok = diff_tyt = diff_ayt = diff_other = 0

        for exam in qs:
            total += 1
            results = list(exam.results.all())
            if not results:
                if options['show_ok']:
                    self.stdout.write(f'[NO_RESULTS] Exam#{exam.id} ({exam.student.full_name})')
                continue

            subject_names = {r.subject.name for r in results}
            ct   = _chart_total(results)
            tnt  = round(exam.total_net(), 2)
            diff = round(tnt - ct, 2)

            if abs(diff) < 0.01:
                ok += 1
                if options['show_ok']:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'[OK      ] Exam#{exam.id:<5} {exam.student.full_name} '
                            f'({exam.exam_date}) chart={ct} total_net={tnt}'
                        )
                    )
                continue

            # Classify the difference
            ayt_net = round(sum(r.net_score for r in results
                                if r.subject.name.startswith('AYT')), 2)
            other_net = round(sum(
                r.net_score for r in results
                if r.subject.name not in _KNOWN_TYT and r.subject.name not in _KNOWN_AYT
            ), 2)

            if ayt_net and abs(diff - ayt_net) < 0.01:
                tag = 'DIFF_AYT  '
                diff_ayt += 1
            elif other_net and abs(diff - other_net) < 0.01:
                tag = 'DIFF_OTHER'
                diff_other += 1
            else:
                tag = 'DIFF_TYT  '
                diff_tyt += 1

            self.stdout.write(
                self.style.WARNING(
                    f'[{tag}] Exam#{exam.id:<5} {exam.student.full_name} '
                    f'({exam.exam_date}) chart={ct} total_net={tnt} diff={diff:+.2f}'
                )
            )
            self.stdout.write(f'           subjects={sorted(subject_names)}')
            if ayt_net:
                self.stdout.write(f'           ayt_net={ayt_net}')
            if other_net:
                self.stdout.write(f'           other_net={other_net}')

        self.stdout.write('')
        self.stdout.write(
            f'Scanned {total} exams: {ok} OK  |  '
            f'{diff_tyt} DIFF_TYT (bug)  |  '
            f'{diff_ayt} DIFF_AYT (ok, AYT subjects)  |  '
            f'{diff_other} DIFF_OTHER (unknown subjects)'
        )
        if diff_tyt:
            self.stdout.write(self.style.ERROR(
                f'ACTION REQUIRED: {diff_tyt} exam(s) have TYT chart totals that '
                f'differ from total_net() — check split-subject aggregation.'
            ))

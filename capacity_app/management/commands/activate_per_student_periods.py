"""
Management command: activate_per_student_periods

DRY RUN by default.  Pass --apply to write.  Pass --coach <id> to limit scope.

Works regardless of COACH_PER_STUDENT_PERIODS flag.  Never changes the flag.

For every active coach (scoped by --coach if given):
  (a) Every active OWN link (is_own_student_source) with null next_payment_due
      → next_payment_due = today + 30.  Links that already have a date are skipped.
  (b) Every currently active CoachCapacityGrant (period_start <= today <= period_end)
      → convert unused slots (slots - in_use own students, floor 0) to a
        CoachCreditLedger row (reason=converted_from_grant).
      Idempotency: notes field carries 'grant_id:<pk>' so a re-run skips grants
      that were already converted.
  (c) One audit row (delta=0, reason=transition_first_period) per coach+run
      that changed something.

Prints a per-coach table and totals in both dry-run and apply modes.
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Set initial next_payment_due and convert active grants to credits. DRY RUN by default.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write changes (default: dry run).')
        parser.add_argument('--coach', type=int, default=None,
                            help='Limit to a single coach by primary key.')

    def handle(self, *args, **options):
        apply = options['apply']
        coach_id = options.get('coach')

        from django.contrib.auth import get_user_model
        from capacity_app.models import CoachCapacityGrant, CoachCreditLedger
        from capacity_app.services import get_capacity_status, is_own_student_source
        from users_app.models import CoachStudent

        User = get_user_model()
        today = date.today()

        coaches_qs = User.objects.filter(role='coach', is_active=True).order_by('full_name')
        if coach_id:
            coaches_qs = coaches_qs.filter(pk=coach_id)

        total_dates = 0
        total_credits = 0
        rows = []

        for coach in coaches_qs:
            own_links = [
                cs for cs in
                CoachStudent.objects.filter(coach=coach, active=True)
                .select_related('student')
                if is_own_student_source(cs.source, cs.student)
            ]

            # (a) links needing a due date
            links_to_date = [cs for cs in own_links if cs.next_payment_due is None]

            # (b) active grants to convert
            active_grants = list(
                CoachCapacityGrant.objects.filter(
                    coach=coach,
                    period_start__lte=today,
                    period_end__gte=today,
                ).order_by('pk')
            )
            in_use = len(own_links)

            credits_to_convert = 0
            grants_to_process = []
            for grant in active_grants:
                marker = f'grant_id:{grant.pk}'
                already = CoachCreditLedger.objects.filter(
                    coach=coach,
                    reason=CoachCreditLedger.REASON_CONVERTED_FROM_GRANT,
                    notes__contains=marker,
                ).exists()
                if already:
                    continue
                unused = max(0, grant.slots - in_use)
                grants_to_process.append((grant, unused))
                credits_to_convert += unused

            existing_balance = sum(
                e.delta for e in CoachCreditLedger.objects.filter(coach=coach)
            ) or 0
            resulting_balance = existing_balance + credits_to_convert

            rows.append({
                'coach':    f'{coach.full_name} ({coach.email})',
                'students': len(own_links),
                'dates':    len(links_to_date),
                'credits':  credits_to_convert,
                'balance':  resulting_balance,
            })
            total_dates   += len(links_to_date)
            total_credits += credits_to_convert

            if apply:
                changed = False
                with transaction.atomic():
                    for cs in links_to_date:
                        cs.next_payment_due = today + timedelta(days=30)
                        cs.save(update_fields=['next_payment_due'])
                        changed = True

                    for grant, unused in grants_to_process:
                        if unused > 0:
                            CoachCreditLedger.objects.create(
                                coach=coach,
                                delta=unused,
                                reason=CoachCreditLedger.REASON_CONVERTED_FROM_GRANT,
                                order=grant.order,
                                notes=f'grant_id:{grant.pk}',
                            )
                            changed = True

                    if changed:
                        CoachCreditLedger.objects.create(
                            coach=coach,
                            delta=0,
                            reason=CoachCreditLedger.REASON_TRANSITION_FIRST_PERIOD,
                            notes=f'Aktivasyon: {today}, öğrenci sayısı: {len(own_links)}',
                        )

        # Print table
        mode = 'APPLY' if apply else 'DRY RUN'
        self.stdout.write(f'\n{mode} — activate_per_student_periods\n')
        header = f'{"Koç":<40} {"Öğr":>5} {"Tarih":>6} {"Kredi":>6} {"Bakiye":>7}'
        self.stdout.write(header)
        self.stdout.write('-' * len(header))
        for r in rows:
            self.stdout.write(
                f'{r["coach"][:40]:<40} {r["students"]:>5} '
                f'{r["dates"]:>6} {r["credits"]:>6} {r["balance"]:>7}'
            )
        self.stdout.write('-' * len(header))
        self.stdout.write(
            f'{"TOPLAM":<40} {"":>5} {total_dates:>6} {total_credits:>6}'
        )
        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    '\nDRY RUN — değişiklik yazılmadı. --apply ile çalıştırın.'
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS('\nDeğişiklikler uygulandı.'))

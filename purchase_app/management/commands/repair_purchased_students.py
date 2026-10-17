"""
Idempotent repair command for purchased students that are missing User.coach or CoachStudent.

Usage:
    python manage.py repair_purchased_students          # dry-run (default)
    python manage.py repair_purchased_students --apply  # write changes
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from purchase_app.models import Order
from users_app.models import CoachStudent

User = get_user_model()


class Command(BaseCommand):
    help = 'Repair purchased students missing User.coach or CoachStudent rows (dry-run by default).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Write repairs to the database (default is dry-run).',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(f'[{mode}] Scanning paid orders...')

        paid_orders = (
            Order.objects
            .filter(status=Order.STATUS_PAID, student__isnull=False)
            .select_related('student', 'coach', 'plan')
        )

        fixed_coach_fk = 0
        fixed_cs_missing = 0
        fixed_cs_inactive = 0
        skipped_conflict = 0

        for order in paid_orders:
            student = order.student
            coach = order.coach

            # Skip non-students (should not happen on paid orders, but be safe)
            if not student.is_student:
                self.stdout.write(
                    self.style.WARNING(
                        f'  Order #{order.pk}: student pk={student.pk} has role={student.role!r} — skipping'
                    )
                )
                continue

            # 1. Check User.coach FK
            if student.coach_id != coach.pk:
                if student.coach_id is not None:
                    # Already assigned to a different coach — leave it, flag for review
                    self.stdout.write(
                        self.style.WARNING(
                            f'  Order #{order.pk}: student pk={student.pk} has coach_id={student.coach_id}'
                            f' but order.coach_id={coach.pk} — skipping User.coach to avoid overwrite'
                        )
                    )
                    skipped_conflict += 1
                else:
                    self.stdout.write(
                        f'  Order #{order.pk}: student pk={student.pk} missing User.coach → set to coach pk={coach.pk}'
                    )
                    if apply:
                        User.objects.filter(pk=student.pk).update(coach=coach)
                    fixed_coach_fk += 1

            # 2. Check CoachStudent row
            cs = CoachStudent.objects.filter(coach=coach, student=student).first()
            if cs is None:
                self.stdout.write(
                    f'  Order #{order.pk}: CoachStudent missing for coach pk={coach.pk} / student pk={student.pk} → create'
                )
                if apply:
                    from datetime import date, timedelta
                    CoachStudent.objects.create(
                        coach=coach,
                        student=student,
                        source=CoachStudent.SOURCE_VAGUS,
                        active=True,
                        next_payment_due=date.today() + timedelta(days=order.plan.duration_days),
                    )
                fixed_cs_missing += 1
            elif not cs.active:
                self.stdout.write(
                    f'  Order #{order.pk}: CoachStudent pk={cs.pk} is inactive → reactivate'
                )
                if apply:
                    cs.active = True
                    cs.deactivation_reason = None
                    cs.save(update_fields=['active', 'deactivation_reason'])
                fixed_cs_inactive += 1

        self.stdout.write('')
        self.stdout.write(f'[{mode}] Results:')
        self.stdout.write(f'  User.coach set:          {fixed_coach_fk}')
        self.stdout.write(f'  CoachStudent created:    {fixed_cs_missing}')
        self.stdout.write(f'  CoachStudent reactivated:{fixed_cs_inactive}')
        self.stdout.write(f'  Conflicts skipped:       {skipped_conflict}')

        if not apply and (fixed_coach_fk or fixed_cs_missing or fixed_cs_inactive):
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Run with --apply to write these changes.'))
        elif apply:
            self.stdout.write(self.style.SUCCESS('Done.'))
        else:
            self.stdout.write(self.style.SUCCESS('Nothing to repair.'))

import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from purchase_app.models import Order

_log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Backfill User.phone for students who have none, '
        'from paid orders where exactly one distinct phone appears. '
        'Dry-run by default; pass --apply to write changes.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Write changes to the database (default is dry-run).',
        )

    def handle(self, *args, **options):
        from users_app.forms import _normalize_tr_phone_e164

        apply = options['apply']
        User = get_user_model()

        students = User.objects.filter(role='student', phone__isnull=True)
        updated = skipped = 0

        for student in students.iterator():
            phones = list(
                Order.objects.filter(student=student, status=Order.STATUS_PAID)
                .exclude(phone='')
                .values_list('phone', flat=True)
                .distinct()
            )
            if len(phones) != 1:
                skipped += 1
                continue
            try:
                e164 = _normalize_tr_phone_e164(phones[0])
            except (ValueError, Exception):
                skipped += 1
                continue

            if apply:
                User.objects.filter(pk=student.pk).update(phone=e164)
                self.stdout.write(f'  updated {student.email}')
            else:
                self.stdout.write(f'  [dry-run] would set {student.email} → {e164}')
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDone: {updated} {"updated" if apply else "would be updated"}, '
                f'{skipped} skipped (no paid orders, multiple phones, or invalid number).'
            )
        )
        if not apply:
            self.stdout.write('Re-run with --apply to write changes.')

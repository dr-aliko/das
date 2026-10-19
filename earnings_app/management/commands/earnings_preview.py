from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Preview how an order\'s earning would split if released on a given date (read-only, no writes).'

    def add_arguments(self, parser):
        parser.add_argument('order_id', type=int, help='Order PK')
        parser.add_argument(
            '--as-of',
            dest='as_of',
            default=None,
            metavar='YYYY-MM-DD',
            help='Use this date as coverage end for the preview (default: computed coverage end).',
        )

    def handle(self, *args, **options):
        from purchase_app.models import Order
        from earnings_app.models import EarningRow
        from earnings_app.services import compute_split
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            order = (
                Order.objects
                .select_related('plan', 'coach', 'student')
                .get(pk=options['order_id'])
            )
        except Order.DoesNotExist:
            raise CommandError(f"Order {options['order_id']} bulunamadı.")

        pool_kurus = order.plan.coach_share_kurus

        # Coverage dates: use existing EarningRow if present, else simulate
        existing = (
            EarningRow.objects
            .filter(order=order)
            .order_by('coverage_start')
            .first()
        )

        if existing:
            coverage_start = existing.coverage_start
            coverage_end   = existing.coverage_end
        else:
            today = date.today()
            prev = (
                EarningRow.objects
                .filter(
                    student_id=order.student_id,
                    status__in=[
                        EarningRow.STATUS_HELD,
                        EarningRow.STATUS_RELEASED,
                        EarningRow.STATUS_APPROVED,
                        EarningRow.STATUS_PAID,
                    ],
                )
                .order_by('-coverage_end')
                .first()
            )
            coverage_start = prev.coverage_end if (prev and prev.coverage_end > today) else today
            coverage_end   = coverage_start + timedelta(days=order.plan.duration_days)

        if options['as_of']:
            try:
                effective_end = date.fromisoformat(options['as_of'])
            except ValueError:
                raise CommandError(f"Geçersiz tarih '{options['as_of']}'. YYYY-MM-DD kullanın.")
        else:
            effective_end = coverage_end

        w = self.stdout.write
        w('')
        w(self.style.HTTP_INFO(
            f'Sipariş #{order.pk}  {order.email}  [{order.get_status_display()}]'
        ))
        w(f'  Plan:     {order.plan.name} ({order.plan.duration_days} gün)')
        w(f'  Öğrenci:  {order.student.full_name if order.student else "—"}')
        w(f'  Kapsam:   {coverage_start} → {coverage_end}')
        if effective_end != coverage_end:
            w(f'  --as-of:  {effective_end}  (kapsam sonu yerine kullanıldı)')
        w(f'  Havuz:    {pool_kurus // 100} TL  ({pool_kurus} kr)')
        w('')

        if not order.student_id:
            w(self.style.WARNING('  Öğrenci atanmamış — kazanç oluşturulamaz.'))
            return

        if pool_kurus <= 0:
            w(self.style.WARNING('  Koç havuzu 0 — kazanç yok.'))
            return

        splits = compute_split(order.student_id, coverage_start, effective_end, pool_kurus)
        period_days = (effective_end - coverage_start).days

        if not splits:
            w(self.style.WARNING('  Koç bulunamadı — kazanç yok.'))
            return

        w(f'  {"Koç":<30}  {"Gün":>5}  {"TL":>8}  {"Kuruş":>10}  Not')
        w('  ' + '-' * 68)

        total_kurus = 0
        for s in splits:
            try:
                coach = User.objects.get(pk=s['coach_id'])
                name = coach.full_name
            except User.DoesNotExist:
                name = f'(id={s["coach_id"]})'
            note = '⚠ boşluk-fallback' if s.get('gap_fallback') else ''
            tl = s['amount_kurus'] // 100
            w(f'  {name:<30}  {s["days"]:>5}  {tl:>8}  {s["amount_kurus"]:>10}  {note}')
            total_kurus += s['amount_kurus']

        w('  ' + '-' * 68)
        w(f'  {"TOPLAM":<30}  {period_days:>5}  {total_kurus // 100:>8}  {total_kurus:>10}')
        w('')

        vagus_kurus = pool_kurus - total_kurus
        vagus_tl    = vagus_kurus // 100
        w(self.style.SUCCESS(f"  Vagus'ta kalan: {vagus_tl} TL  ({vagus_kurus} kr)"))
        w('')

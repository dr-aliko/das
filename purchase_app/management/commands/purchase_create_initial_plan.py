from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create the default "1 aylık" plan if it does not already exist.'

    def handle(self, *args, **options):
        from purchase_app.models import Plan

        plan, created = Plan.objects.get_or_create(
            name='1 aylık',
            defaults={
                'kind':          Plan.KIND_ONE_TIME,
                'price_kurus':   319900,
                'duration_days': 30,
                'active':        True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(
                f'Created plan: {plan} (pk={plan.pk})'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f'Plan already exists: {plan} (pk={plan.pk})'
            ))

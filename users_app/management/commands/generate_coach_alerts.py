from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Generate proactive coaching inbox alerts for all coaches.'

    def add_arguments(self, parser):
        parser.add_argument('--coach-id', type=int, default=None,
                            help='Run for a single coach (default: all coaches)')

    def handle(self, *args, **options):
        from users_app.services.alert_engine import generate_alerts_for_coach

        coaches = (
            User.objects.filter(id=options['coach_id'], role='coach')
            if options['coach_id']
            else User.objects.filter(role='coach', is_active=True)
        )

        total_created = total_updated = 0
        for coach in coaches:
            created, updated = generate_alerts_for_coach(coach)
            total_created += created
            total_updated += updated
            self.stdout.write(
                f'  {coach.full_name}: +{created} new, {updated} refreshed'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Done. {total_created} created, {total_updated} refreshed '
            f'across {coaches.count()} coach(es).'
        ))

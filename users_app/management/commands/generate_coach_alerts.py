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
        from users_app.tasks import generate_all_coach_alerts

        if options['coach_id']:
            coach = User.objects.get(id=options['coach_id'], role='coach')
            created, updated = generate_alerts_for_coach(coach)
            self.stdout.write(f'  {coach.full_name}: +{created} new, {updated} refreshed')
            self.stdout.write(self.style.SUCCESS(
                f'Done. {created} created, {updated} refreshed.'
            ))
        else:
            created, updated = generate_all_coach_alerts()
            self.stdout.write(self.style.SUCCESS(
                f'Done. {created} created, {updated} refreshed.'
            ))

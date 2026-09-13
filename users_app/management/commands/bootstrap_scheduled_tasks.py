from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Register (or refresh) Django-Q2 periodic tasks. Safe to run multiple times.'

    def handle(self, *args, **options):
        from django_q.models import Schedule

        schedule, created = Schedule.objects.update_or_create(
            func='users_app.tasks.generate_all_coach_alerts',
            defaults={
                'name': 'Generate coach alerts (every 30 min)',
                'schedule_type': Schedule.MINUTES,
                'minutes': 30,
                'repeats': -1,
            },
        )
        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} schedule: {schedule.name} (every {schedule.minutes} min)'
        ))

        # Django-Q2 evaluates cron in Django's TIME_ZONE (Europe/Istanbul) — use local time directly
        schedule, created = Schedule.objects.update_or_create(
            func='users_app.tasks.send_task_deadline_reminders',
            defaults={
                'name': 'Task deadline reminders (daily 09:00 Istanbul)',
                'schedule_type': Schedule.CRON,
                'cron': '0 9 * * *',
                'repeats': -1,
            },
        )
        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} schedule: {schedule.name}'
        ))

        schedule, created = Schedule.objects.update_or_create(
            func='users_app.tasks.send_motivational_notifications',
            defaults={
                'name': 'Motivational push notifications (daily 19:00 Istanbul)',
                'schedule_type': Schedule.CRON,
                'cron': '0 19 * * *',
                'repeats': -1,
            },
        )
        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(
            f'{action} schedule: {schedule.name}'
        ))

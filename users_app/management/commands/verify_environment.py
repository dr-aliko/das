import os

from decouple import config
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Print non-sensitive environment + DB status for production troubleshooting. Never prints passwords."

    def handle(self, *args, **options):
        out = self.stdout
        ok = self.style.SUCCESS
        warn = self.style.WARNING
        err = self.style.ERROR

        out.write("=== Environment ===")
        out.write(f"  CWD:                         {os.getcwd()}")
        out.write(f"  DEBUG:                       {settings.DEBUG}")
        out.write(f"  ALLOWED_HOSTS:               {settings.ALLOWED_HOSTS}")
        out.write(f"  DATABASE_URL in os.environ:  {'yes' if os.environ.get('DATABASE_URL') else 'no'}")
        out.write(f"  DATABASE_URL via decouple:   {'yes' if config('DATABASE_URL', default='') else 'no'}")

        out.write("")
        out.write("=== Database (live connection) ===")
        db = settings.DATABASES['default']
        out.write(f"  ENGINE:        {db.get('ENGINE')}")
        out.write(f"  NAME:          {db.get('NAME')}")
        out.write(f"  HOST:          {db.get('HOST') or '(default)'}")
        out.write(f"  PORT:          {db.get('PORT') or '(default)'}")
        out.write(f"  USER:          {db.get('USER') or '(default)'}")
        out.write(f"  CONN_MAX_AGE:  {db.get('CONN_MAX_AGE')}")
        out.write(f"  vendor (live): {connection.vendor}")
        if connection.vendor == 'sqlite' and not settings.DEBUG:
            out.write(warn("  WARNING: SQLite engine in a non-DEBUG environment. "
                           "DATABASE_URL was not loaded — check the shell env."))

        out.write("")
        out.write("=== Django-Q2 ===")
        in_apps = 'django_q' in settings.INSTALLED_APPS
        out.write(f"  django_q in INSTALLED_APPS: {'yes' if in_apps else 'no'}")
        q_cluster = getattr(settings, 'Q_CLUSTER', {})
        out.write(f"  Q_CLUSTER broker (orm):     {q_cluster.get('orm') or '(not set)'}")
        out.write(f"  Q_CLUSTER sync mode:        {q_cluster.get('sync', False)}")

        required = {'django_q_ormq', 'django_q_schedule', 'django_q_task'}
        existing = set(connection.introspection.table_names())
        missing = required - existing
        if missing:
            out.write(err(f"  Missing django_q tables: {sorted(missing)}"))
            out.write(err("  → Fix: python manage.py migrate django_q"))
        else:
            out.write(ok("  All required django_q tables exist."))

        out.write("")
        out.write("=== Scheduled Tasks ===")
        try:
            from django_q.models import Schedule
            schedules = list(Schedule.objects.values_list('name', 'func', 'minutes'))
            out.write(f"  Count: {len(schedules)}")
            for name, func, minutes in schedules:
                out.write(f"    - {name}: {func} (every {minutes} min)")
            if not schedules:
                out.write(warn("    (none — run: python manage.py bootstrap_scheduled_tasks)"))
        except Exception as e:
            out.write(err(f"  Schedule query failed: {e.__class__.__name__}: {e}"))

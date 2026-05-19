import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        'Creates a pg_dump backup of the Postgres database and rotates old backups. '
        'Safe to schedule via cron or systemd timer.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--backup-dir',
            default='/srv/das/backups/',
            help='Directory to write dump files (default: /srv/das/backups/)',
        )
        parser.add_argument(
            '--keep-days',
            type=int,
            default=14,
            help='Delete backups older than this many days (default: 14)',
        )

    def handle(self, *args, **options):
        backup_dir = Path(options['backup_dir'])
        keep_days = options['keep_days']

        db = settings.DATABASES['default']
        engine = db.get('ENGINE', '')
        if 'postgresql' not in engine and 'postgis' not in engine:
            raise CommandError(
                f'backup_db only supports PostgreSQL backends. '
                f'Current ENGINE: {engine}'
            )

        backup_dir.mkdir(parents=True, exist_ok=True)

        db_name = db.get('NAME', 'vagus_db')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        out_file = backup_dir / f'{db_name}_{timestamp}.dump'

        env = os.environ.copy()
        if db.get('PASSWORD'):
            env['PGPASSWORD'] = db['PASSWORD']

        cmd = ['pg_dump', '--format=custom', '--no-acl', '--no-owner']
        if db.get('HOST'):
            cmd += ['--host', db['HOST']]
        if db.get('PORT'):
            cmd += ['--port', str(db['PORT'])]
        if db.get('USER'):
            cmd += ['--username', db['USER']]
        cmd += [db_name, '--file', str(out_file)]

        self.stdout.write(f'Backing up "{db_name}" → {out_file} …')
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if result.returncode != 0:
            raise CommandError(f'pg_dump failed:\n{result.stderr.strip()}')

        size_mb = out_file.stat().st_size / (1024 * 1024)
        self.stdout.write(
            self.style.SUCCESS(
                f'Done: {out_file.name} ({size_mb:.1f} MB)'
            )
        )

        # Rotate: delete .dump files older than keep_days
        cutoff = datetime.now() - timedelta(days=keep_days)
        deleted = [
            f for f in backup_dir.glob('*.dump')
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff
        ]
        for f in deleted:
            f.unlink()

        if deleted:
            self.stdout.write(
                f'Rotated {len(deleted)} backup(s) older than {keep_days} days.'
            )

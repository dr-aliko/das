"""
Upsert KonuTakipTopic records from a JSON file.

Expected JSON format:
{
  "TYT Biyoloji": ["Konu 1", "Konu 2", ...],
  "TYT Matematik": [
    "Konu 1",
    {"name": "Problemler", "checkable": false, "children": ["Alt Konu 1", ...]},
    "Konu 3"
  ]
}

Run: python manage.py seed_konu_topics --file topics.json
"""
import json

from django.core.management.base import BaseCommand, CommandError

from exams_app.models import Subject
from konu_takip_app.models import KonuTakipTopic


class Command(BaseCommand):
    help = 'Upsert KonuTakipTopic records from a JSON file (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--file', required=True, help='Path to topics JSON file.')

    def handle(self, *args, **opts):
        path = opts['file']
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'File not found: {path}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON: {e}')

        total_created = total_updated = 0

        for subject_name, topic_list in data.items():
            try:
                subject = Subject.objects.get(name=subject_name)
            except Subject.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f'  SKIP: Subject "{subject_name}" not found — add it first.'
                ))
                continue

            self.stdout.write(f'\n{subject_name}:')

            for i, entry in enumerate(topic_list):
                if isinstance(entry, str):
                    topic, created = self._upsert(subject, None, entry, i, True)
                    self._log(topic.name, created)
                    if created:
                        total_created += 1
                    else:
                        total_updated += 1

                elif isinstance(entry, dict):
                    parent_name = entry['name']
                    checkable = entry.get('checkable', True)
                    parent, created = self._upsert(subject, None, parent_name, i, checkable)
                    self._log(parent_name, created, indent=0)
                    if created:
                        total_created += 1
                    else:
                        total_updated += 1

                    for j, child_name in enumerate(entry.get('children', [])):
                        child, child_created = self._upsert(subject, parent, child_name, j, True)
                        self._log(child_name, child_created, indent=2)
                        if child_created:
                            total_created += 1
                        else:
                            total_updated += 1
                else:
                    self.stdout.write(self.style.WARNING(f'  SKIP: unexpected entry type: {entry!r}'))

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: {total_created} created, {total_updated} updated.'
        ))

    def _upsert(self, subject, parent, name, order, checkable):
        # Use filter+first to correctly handle nullable parent (NULL != NULL in UNIQUE).
        lookup = KonuTakipTopic.objects.filter(
            subject=subject,
            name=name,
            parent=parent,
        )
        existing = lookup.first()
        if existing:
            changed = False
            if existing.order != order:
                existing.order = order
                changed = True
            if existing.checkable != checkable:
                existing.checkable = checkable
                changed = True
            if changed:
                existing.save(update_fields=['order', 'checkable'])
            return existing, False
        else:
            topic = KonuTakipTopic.objects.create(
                subject=subject,
                parent=parent,
                name=name,
                order=order,
                checkable=checkable,
            )
            return topic, True

    def _log(self, name, created, indent=0):
        prefix = '  ' * indent
        tag = self.style.SUCCESS('  CREATE') if created else '  update'
        self.stdout.write(f'{prefix}{tag} {name}')

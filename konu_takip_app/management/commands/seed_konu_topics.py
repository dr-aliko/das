"""
Upsert KonuTakipTopic records from a JSON file (idempotent, any nesting depth).

Expected JSON format:
{
  "TYT Biyoloji": ["Konu 1", "Konu 2", ...],
  "AYT Fizik": [
    {"name": "9. Sınıf Fizik", "checkable": false, "children": [
      "Fizik Bilimine Giriş",
      {"name": "Kuvvet ve Hareket", "checkable": false, "children": [
        "Bir Boyutta Hareket", "Kuvvet"
      ]}
    ]}
  ]
}

Children arrays may mix plain strings (leaf topics) and nested dict objects
(sub-category headers with their own children) at any depth.

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
            c, u = self._process_entries(subject, None, topic_list, indent=0)
            total_created += c
            total_updated += u

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: {total_created} created, {total_updated} updated.'
        ))

    def _process_entries(self, subject, parent, entries, indent):
        """Recursively upsert entries; children may be strings or nested dicts."""
        created = updated = 0
        for i, entry in enumerate(entries):
            if isinstance(entry, str):
                topic, c = self._upsert(subject, parent, entry, i, True)
                self._log(entry, c, indent)
                created += c
                updated += 1 - c
            elif isinstance(entry, dict):
                name = entry['name']
                checkable = entry.get('checkable', True)
                topic, c = self._upsert(subject, parent, name, i, checkable)
                self._log(name, c, indent)
                created += c
                updated += 1 - c
                if 'children' in entry:
                    cc, cu = self._process_entries(subject, topic, entry['children'], indent + 2)
                    created += cc
                    updated += cu
            else:
                self.stdout.write(self.style.WARNING(f'  SKIP: unexpected entry type: {entry!r}'))
        return created, updated

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

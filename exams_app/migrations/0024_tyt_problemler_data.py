from django.db import migrations

PROBLEMLER_TOPICS = [
    'Problemler - Grafik',
    'Problemler - Hareket ve Hız',
    'Problemler - İşçi Emek',
    'Problemler - Kar Zarar',
    'Problemler - Karışım',
    'Problemler - Kesir',
    'Problemler - Rutin Olmayan',
    'Problemler - Sayı',
    'Problemler - Yaş',
    'Problemler - Yüzde',
]


def create_tyt_problemler(apps, schema_editor):
    Subject = apps.get_model('exams_app', 'Subject')
    Topic = apps.get_model('exams_app', 'Topic')

    subject, _ = Subject.objects.get_or_create(
        exam_type='TYT',
        name='TYT Problemler',
        defaults={'question_count': 12, 'excluded_from_planning': True},
    )
    subject.question_count = 12
    subject.excluded_from_planning = True
    subject.save()

    for name in PROBLEMLER_TOPICS:
        Topic.objects.get_or_create(
            subject=subject,
            name=name,
            defaults={'sub_category': '', 'order_index': 9999},
        )


def remove_tyt_problemler(apps, schema_editor):
    Subject = apps.get_model('exams_app', 'Subject')
    Subject.objects.filter(exam_type='TYT', name='TYT Problemler').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('exams_app', '0023_bransdeneme_soru_sayisi'),
    ]

    operations = [
        migrations.RunPython(create_tyt_problemler, remove_tyt_problemler),
    ]

from django.db import migrations, models

CURATED_PUBLISHERS = [
    '345 (Üç Dört Beş)',
    'Bilgi Sarmal',
    'Orijinal Yayınları',
    'Limit Yayınları',
    'Apotemi',
    'Hız ve Renk',
    'Özdebir Yayınları',
    '3D Yayınları',
    'Paraf Yayınları',
    'TÖDER',
]


def seed_curated_publishers(apps, schema_editor):
    Publisher = apps.get_model('exams_app', 'Publisher')
    Publisher.objects.exclude(name__in=CURATED_PUBLISHERS).update(is_active=False)
    for name in CURATED_PUBLISHERS:
        Publisher.objects.update_or_create(name=name, defaults={'is_active': True})


def unseed_curated_publishers(apps, schema_editor):
    Publisher = apps.get_model('exams_app', 'Publisher')
    Publisher.objects.update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('exams_app', '0018_topic_order_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='publisher',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(seed_curated_publishers, unseed_curated_publishers),
    ]

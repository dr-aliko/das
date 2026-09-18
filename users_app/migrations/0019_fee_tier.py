from decimal import Decimal
from django.db import migrations, models


def seed_fee_tiers(apps, schema_editor):
    FeeTier = apps.get_model('users_app', 'FeeTier')

    vagus = [
        # (order, min_students, max_students, monthly_fee_try)
        (1,  1,  1,    Decimal('0')),
        (2,  2,  3,    Decimal('1200')),
        (3,  4,  6,    Decimal('2400')),
        (4,  7,  10,   Decimal('3600')),
        (5,  11, 15,   Decimal('4800')),
        (6,  16, None, Decimal('6000')),
    ]
    coach = [
        (1,  1,  1,    Decimal('250')),  # 1 student, no free tier (spec: 250 TL)
        (2,  2,  3,    Decimal('800')),
        (3,  4,  6,    Decimal('1600')),
        (4,  7,  10,   Decimal('2400')),
        (5,  11, 15,   Decimal('3200')),
        (6,  16, None, Decimal('4000')),
    ]

    for source, tiers in [('vagus', vagus), ('coach', coach)]:
        for order, min_s, max_s, fee in tiers:
            FeeTier.objects.create(
                source=source,
                order=order,
                min_students=min_s,
                max_students=max_s,
                monthly_fee_try=fee,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0018_coachstudent_billing'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeeTier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(
                    choices=[('vagus', 'Vagus'), ('coach', 'Koç')],
                    db_index=True, max_length=10,
                )),
                ('min_students', models.PositiveIntegerField()),
                ('max_students', models.PositiveIntegerField(blank=True, null=True)),
                ('monthly_fee_try', models.DecimalField(decimal_places=2, max_digits=9)),
                ('order', models.PositiveIntegerField()),
            ],
            options={
                'verbose_name': 'Ücret Tarifesi',
                'verbose_name_plural': 'Ücret Tarifeleri',
                'ordering': ['source', 'order'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='feetier',
            unique_together={('source', 'order')},
        ),
        migrations.RunPython(seed_fee_tiers, migrations.RunPython.noop),
    ]

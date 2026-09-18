"""
Corrects the coach source, order=1 tier from 800 TL to the spec value of 250 TL.
The original seed in 0019 mistakenly duplicated the 2-3 band value (800) into the
1-student band instead of the correct 250 TL.
"""
from decimal import Decimal
from django.db import migrations


def fix_coach_tier1(apps, schema_editor):
    FeeTier = apps.get_model('users_app', 'FeeTier')
    FeeTier.objects.filter(source='coach', order=1, monthly_fee_try=Decimal('800')).update(
        monthly_fee_try=Decimal('250')
    )


def reverse_fix(apps, schema_editor):
    FeeTier = apps.get_model('users_app', 'FeeTier')
    FeeTier.objects.filter(source='coach', order=1, monthly_fee_try=Decimal('250')).update(
        monthly_fee_try=Decimal('800')
    )


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0019_fee_tier'),
    ]

    operations = [
        migrations.RunPython(fix_coach_tier1, reverse_fix),
    ]

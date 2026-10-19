from django.db import migrations


def set_1aylik_coach_share(apps, schema_editor):
    Plan = apps.get_model('purchase_app', 'Plan')
    updated = Plan.objects.filter(name__icontains='1 aylık').update(coach_share_kurus=250000)
    if not updated:
        # Fallback: set on the cheapest active plan if the name doesn't match
        cheapest = Plan.objects.filter(active=True).order_by('price_kurus').first()
        if cheapest:
            Plan.objects.filter(pk=cheapest.pk).update(coach_share_kurus=250000)


class Migration(migrations.Migration):

    dependencies = [
        ('purchase_app', '0005_plan_coach_share_kurus'),
    ]

    operations = [
        migrations.RunPython(set_1aylik_coach_share, migrations.RunPython.noop),
    ]

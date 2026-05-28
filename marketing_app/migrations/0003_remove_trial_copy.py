from django.db import migrations


def remove_trial_copy(apps, schema_editor):
    SiteSettings = apps.get_model('marketing_app', 'SiteSettings')
    PricingPlan = apps.get_model('marketing_app', 'PricingPlan')
    FAQItem = apps.get_model('marketing_app', 'FAQItem')

    SiteSettings.objects.filter(pk=1, final_cta_subtitle__contains='14 gün').update(
        final_cta_subtitle='Kredi kartı gerekmez. Kayıt 60 saniye.'
    )

    PricingPlan.objects.filter(cta_label='14 Gün Ücretsiz Başla').update(
        cta_label='Hemen Başla'
    )

    FAQItem.objects.filter(question='14 günlük denemede ne yapabilirim?').update(
        question='Deneme döneminde ne yapabilirim?'
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_app', '0002_initial_content'),
    ]

    operations = [
        migrations.RunPython(remove_trial_copy, noop),
    ]

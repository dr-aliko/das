from django.db import migrations


def create_site_settings(apps, schema_editor):
    SiteSettings = apps.get_model('marketing_app', 'SiteSettings')
    if not SiteSettings.objects.filter(pk=1).exists():
        SiteSettings.objects.create(
            pk=1,
            hero_eyebrow='YKS 2027 · Akıllı çalışma platformu',
            hero_title_line1='YKS hazırlığını',
            hero_title_line2='plansız bırakma.',
            hero_subtitle=(
                'Vagus; deneme analizlerini, konu eksiklerini, haftalık görevlerini ve '
                'TYT/AYT yol haritanı tek panelde takip etmeni sağlar. '
                'Ne çalışacağını, ne zaman çalışacağını ve nasıl geliştiğini net gör.'
            ),
            hero_cta_primary_label='Hemen Başla',
            hero_cta_primary_url='/auth/register/',
            hero_cta_secondary_label='Demo İncele',
            hero_cta_secondary_url='/ozellikler/',
            final_cta_title='YKS sürecini bugün düzene koy.',
            final_cta_subtitle='14 gün ücretsiz. Kredi kartı gerekmez. Kayıt 60 saniye.',
            nav_cta_label='Hemen Başla',
            nav_cta_url='/auth/register/',
            footer_tagline=(
                'YKS hazırlığında ne çalışacağını, ne zaman çalışacağını ve nasıl '
                'geliştiğini net gösteren akıllı çalışma platformu.'
            ),
            footer_copyright='© 2026 Vagus.',
            footer_location='Ankara · Türkiye',
            contact_email='hello@vagus.app',
            contact_corporate_email='kurumsal@vagus.app',
            contact_whatsapp='+90 532 444 55 66',
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_app', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_site_settings, noop),
    ]

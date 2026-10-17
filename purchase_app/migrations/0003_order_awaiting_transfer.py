from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase_app', '0002_order_sinif_alan'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending',           'Bekliyor'),
                    ('awaiting_transfer', 'Havale Bekleniyor'),
                    ('paid',              'Ödendi'),
                    ('failed',            'Başarısız'),
                    ('cancelled',         'İptal Edildi'),
                    ('refunded',          'İade Edildi'),
                    ('needs_review',      'İnceleme Gerekiyor'),
                ],
                db_index=True,
                default='pending',
                max_length=20,
            ),
        ),
    ]

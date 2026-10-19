from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase_app', '0004_order_claim_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='coach_share_kurus',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Koça ödenecek havuz (kuruş). Ör. 250000 = 2.500,00 ₺',
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase_app', '0003_order_awaiting_transfer'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='payment_claimed_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_sender_name',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
    ]

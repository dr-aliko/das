from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('purchase_app', '0007_purchaseconsent'),
    ]
    operations = [
        migrations.AddField(
            model_name='order',
            name='is_renewal',
            field=models.BooleanField(default=False),
        ),
    ]

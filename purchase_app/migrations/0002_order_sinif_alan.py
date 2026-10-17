from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='sinif',
            field=models.CharField(blank=True, default='', max_length=5),
        ),
        migrations.AddField(
            model_name='order',
            name='alan',
            field=models.CharField(blank=True, default='', max_length=5),
        ),
    ]

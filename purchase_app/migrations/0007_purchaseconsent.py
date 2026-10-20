import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase_app', '0006_data_plan_1aylik_coach_share'),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseConsent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=64)),
                ('text', models.TextField()),
                ('accepted', models.BooleanField()),
                ('doc_version', models.CharField(max_length=32)),
                ('doc_urls', models.JSONField(default=list)),
                ('accepted_at', models.DateTimeField()),
                ('client_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, default='', max_length=512)),
                ('order', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='consents',
                    to='purchase_app.order',
                )),
            ],
            options={
                'verbose_name': 'Satın Alma Onayı',
                'verbose_name_plural': 'Satın Alma Onayları',
            },
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0030_fix_document_storage'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]

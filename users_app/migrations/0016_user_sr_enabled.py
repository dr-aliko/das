from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0015_pushsubscription'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='sr_enabled',
            field=models.BooleanField(default=True),
        ),
    ]

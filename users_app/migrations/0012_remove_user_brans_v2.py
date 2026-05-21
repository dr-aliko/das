from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0011_streak_and_achievements'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='brans_v2',
        ),
    ]

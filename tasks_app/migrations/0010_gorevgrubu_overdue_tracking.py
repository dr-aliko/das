from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks_app', '0009_youtubeplaylist_unique_per_coach'),
    ]

    operations = [
        migrations.AddField(
            model_name='gorevgrubu',
            name='original_tarih',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='gorevgrubu',
            name='last_moved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

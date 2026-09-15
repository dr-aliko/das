from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks_app', '0008_remove_gorevgrubu_tekrar_quality'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Drop the single-column unique constraint on playlist_id
        migrations.AlterField(
            model_name='youtubeplaylist',
            name='playlist_id',
            field=models.CharField(max_length=64),
        ),
        # Add composite unique constraint (playlist_id, imported_by) so each coach
        # gets an independent row for the same YouTube playlist.
        migrations.AlterUniqueTogether(
            name='youtubeplaylist',
            unique_together={('playlist_id', 'imported_by')},
        ),
    ]

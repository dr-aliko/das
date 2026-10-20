from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tasks_app', '0010_gorevgrubu_overdue_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='youtubeplaylist',
            name='last_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='YouTubeImportJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('playlist_id', models.CharField(max_length=64)),
                ('status', models.CharField(default='queued', max_length=16)),
                ('progress_msg', models.CharField(blank=True, max_length=255)),
                ('result_msg', models.CharField(blank=True, max_length=255)),
                ('error_msg', models.CharField(blank=True, max_length=500)),
                ('playlist_pk', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('coach', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='yt_import_jobs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'YouTube Import Job',
                'verbose_name_plural': 'YouTube Import Jobs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='youtubeimportjob',
            index=models.Index(fields=['coach', 'playlist_id', 'status'], name='yt_import_job_idx'),
        ),
    ]

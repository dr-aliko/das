from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('konu_takip_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='studenttopicprogress',
            name='next_review_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='studenttopicprogress',
            name='last_reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='studenttopicprogress',
            name='current_interval_days',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='studenttopicprogress',
            name='ease_factor',
            field=models.FloatField(default=2.5),
        ),
        migrations.AddField(
            model_name='studenttopicprogress',
            name='review_count',
            field=models.PositiveIntegerField(default=0),
        ),
    ]

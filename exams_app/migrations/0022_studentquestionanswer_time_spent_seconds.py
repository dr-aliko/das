from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams_app', '0021_examquestion_subject'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentquestionanswer',
            name='time_spent_seconds',
            field=models.PositiveIntegerField(default=0),
        ),
    ]

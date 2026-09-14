from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams_app', '0022_studentquestionanswer_time_spent_seconds'),
    ]

    operations = [
        migrations.AddField(
            model_name='bransdeneme',
            name='soru_sayisi',
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Soru Sayısı'),
        ),
    ]

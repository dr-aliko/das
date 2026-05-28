from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams_app', '0017_topic_excluded_from_planning'),
    ]

    operations = [
        migrations.AddField(
            model_name='topic',
            name='order_index',
            field=models.PositiveSmallIntegerField(
                default=9999,
                verbose_name='Pedagojik Sıra',
                help_text='Konu havuzunda gösterim sırası. Küçük = önce. 9999 = sırasız.',
            ),
        ),
        migrations.AlterModelOptions(
            name='topic',
            options={
                'verbose_name': 'Konu',
                'verbose_name_plural': 'Konular',
                'ordering': ['subject', 'order_index', 'sub_category', 'name'],
            },
        ),
    ]

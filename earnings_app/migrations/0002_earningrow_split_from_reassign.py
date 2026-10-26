from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('earnings_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='earningrow',
            name='split_from_reassign',
            field=models.BooleanField(
                default=False,
                help_text='Koç değişikliği sırasında orantısal bölünme ile oluşturuldu',
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0017_notification'),
    ]

    operations = [
        migrations.AddField(
            model_name='coachstudent',
            name='source',
            field=models.CharField(
                blank=True,
                choices=[('vagus', 'Vagus'), ('coach', 'Koç')],
                max_length=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='coachstudent',
            name='next_payment_due',
            field=models.DateField(blank=True, null=True),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0020_fix_coach_tier1_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentinvite',
            name='initiated_by_staff',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='studentinvite',
            name='start_date',
            field=models.DateField(null=True, blank=True),
        ),
    ]

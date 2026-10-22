from django.db import migrations, models


def _empty_to_null(apps, schema_editor):
    User = apps.get_model('users_app', 'User')
    User.objects.filter(phone='').update(phone=None)


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0031_user_phone'),
    ]

    operations = [
        # Step 1: allow NULL so we can convert empty strings in the next step
        migrations.AlterField(
            model_name='user',
            name='phone',
            field=models.CharField(blank=True, default=None, max_length=20, null=True),
        ),
        # Step 2: turn '' → NULL (NULLs don't participate in the UNIQUE constraint)
        migrations.RunPython(_empty_to_null, migrations.RunPython.noop),
        # Step 3: enforce uniqueness; multiple NULLs are still allowed by PostgreSQL
        migrations.AlterField(
            model_name='user',
            name='phone',
            field=models.CharField(blank=True, default=None, max_length=20, null=True, unique=True),
        ),
    ]

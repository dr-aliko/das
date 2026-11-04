import struggle_app.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('struggle_app', '0002_add_text_fields_nullable_image'),
    ]

    operations = [
        migrations.AlterField(
            model_name='studentstrugglequestion',
            name='question_image',
            field=models.ImageField(blank=True, null=True, upload_to=struggle_app.models._struggle_q_upload),
        ),
        migrations.AlterField(
            model_name='studentstrugglequestion',
            name='solution_image',
            field=models.ImageField(blank=True, null=True, upload_to=struggle_app.models._struggle_s_upload),
        ),
    ]

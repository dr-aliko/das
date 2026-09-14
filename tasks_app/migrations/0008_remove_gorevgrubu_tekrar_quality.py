from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks_app', '0007_gorevgrubu_student_note_time_spent'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='gorevgrubu',
            name='tekrar_quality',
        ),
    ]

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users_app', '0021_studentinvite_staff_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='EmailVerificationCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=6)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='email_verification',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'E-posta Dogrulama Kodu',
                'verbose_name_plural': 'E-posta Dogrulama Kodlari',
            },
        ),
    ]

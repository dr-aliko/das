import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_DEFAULT_TITLE = 'Kontenjan nasıl çalışır?'

_DEFAULT_BODY = (
    "Kendi öğrencileriniz: Kontenjan, Vagus'ta aynı anda takip edebileceğiniz kendi "
    "öğrenci sayınızdır — yani kendiniz davet ettiğiniz öğrenciler.\n"
    "30 günlük dönem: Dönemler 30 gün sürer; ayrılan öğrencinin slotu serbest kalır "
    "ve yeniden kullanılabilir.\n"
    "Vagus öğrencileri: Vagus'un size atadığı öğrenciler kontenjanınızdan sayılmaz.\n"
    "Dönem sonu: Dönem sona erdiğinde mevcut öğrencileriniz etkilenmez; yenileme "
    "yapana kadar yalnızca yeni öğrenci ekleme kısıtlanır."
)


def seed_explanation(apps, schema_editor):
    CapacitySettings = apps.get_model('capacity_app', 'CapacitySettings')
    CapacitySettings.objects.filter(pk=1).update(
        explanation_title=_DEFAULT_TITLE,
        explanation_body=_DEFAULT_BODY,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('capacity_app', '0002_grantadjustmentlog'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='capacitysettings',
            name='explanation_title',
            field=models.CharField(
                blank=True, default='Kontenjan nasıl çalışır?', max_length=200
            ),
        ),
        migrations.AddField(
            model_name='capacitysettings',
            name='explanation_body',
            field=models.TextField(
                blank=True, default='',
                help_text=(
                    'Her satır bir madde. '
                    '"Başlık: açıklama" → başlık kalın gösterilir. '
                    '"! not" satırı vurgulu kutu olur. En fazla 8 madde, 1500 karakter.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='capacitysettings',
            name='updated_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterModelOptions(
            name='capacitysettings',
            options={
                'verbose_name': 'Kontenjan Ayarları',
                'verbose_name_plural': 'Kontenjan Ayarları',
            },
        ),
        migrations.RunPython(seed_explanation, migrations.RunPython.noop),
    ]

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('purchase_app', '0005_plan_coach_share_kurus'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EarningConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider_commission_pct', models.DecimalField(
                    decimal_places=2, default=0, max_digits=5,
                    help_text='Ödeme sağlayıcı komisyonu (% BRÜT gösterim için bilgi amaçlı)',
                )),
                ('tax_pct', models.DecimalField(
                    decimal_places=2, default=0, max_digits=5,
                    help_text='Vergi oranı (% BRÜT gösterim için bilgi amaçlı)',
                )),
            ],
            options={
                'verbose_name': 'Kazanç Yapılandırması',
                'verbose_name_plural': 'Kazanç Yapılandırması',
            },
        ),
        migrations.CreateModel(
            name='ManualPaymentRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_kurus', models.PositiveIntegerField(help_text='Tam ödeme tutarı (kuruş)')),
                ('coach_pool_kurus', models.PositiveIntegerField(help_text='Koça gidecek havuz (kuruş)')),
                ('date', models.DateField(help_text='Kapsam başlangıç tarihi')),
                ('days', models.PositiveIntegerField(help_text='Kapsam süresi (gün)')),
                ('note', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('coach', models.ForeignKey(
                    limit_choices_to={'role': 'coach'},
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='manual_payment_coach_records',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('created_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='created_manual_payment_records',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('student', models.ForeignKey(
                    limit_choices_to={'role': 'student'},
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='manual_payment_records',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Manuel Ödeme Kaydı',
                'verbose_name_plural': 'Manuel Ödeme Kayıtları',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='EarningRow',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('coverage_start', models.DateField()),
                ('coverage_end', models.DateField(help_text='Kapsam bitiş (dahil değil)')),
                ('period_days', models.PositiveIntegerField()),
                ('coach_days', models.PositiveIntegerField()),
                ('pool_kurus', models.PositiveIntegerField(help_text='Toplam koç havuzu snapshotu (kuruş)')),
                ('amount_kurus', models.IntegerField(help_text='İşaretli kuruş; negatif = düzeltme')),
                ('kind', models.CharField(
                    choices=[('earning', 'Kazanç'), ('adjustment', 'Düzeltme')],
                    default='earning', max_length=12,
                )),
                ('status', models.CharField(
                    choices=[
                        ('held', 'Beklemede'),
                        ('released', 'Serbest'),
                        ('approved', 'Onaylandı'),
                        ('paid', 'Ödendi'),
                        ('void', 'İptal'),
                    ],
                    db_index=True, default='held', max_length=10,
                )),
                ('gap_fallback', models.BooleanField(
                    default=False,
                    help_text='Aralık günlüğü boşluğu; mevcut koça atandı',
                )),
                ('payout_ref', models.CharField(blank=True, default='', max_length=255)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('voided_at', models.DateTimeField(blank=True, null=True)),
                ('void_reason', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('approved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='approved_earnings',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('coach', models.ForeignKey(
                    limit_choices_to={'role': 'coach'},
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='earning_rows',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('manual_record', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='earning_rows',
                    to='earnings_app.manualpaymentrecord',
                )),
                ('order', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='earning_rows',
                    to='purchase_app.order',
                )),
                ('paid_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='paid_out_earnings',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('student', models.ForeignKey(
                    limit_choices_to={'role': 'student'},
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='student_earning_rows',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('voided_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='voided_earnings',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Kazanç Satırı',
                'verbose_name_plural': 'Kazanç Satırları',
                'ordering': ['-coverage_start', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='earningrow',
            index=models.Index(fields=['coach', 'status'], name='earnings_ap_coach_i_idx'),
        ),
        migrations.AddIndex(
            model_name='earningrow',
            index=models.Index(fields=['order', 'status'], name='earnings_ap_order_s_idx'),
        ),
        migrations.AddIndex(
            model_name='earningrow',
            index=models.Index(fields=['coverage_end', 'status'], name='earnings_ap_covend_idx'),
        ),
    ]

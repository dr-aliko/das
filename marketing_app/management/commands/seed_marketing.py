"""
Idempotent command: creates demo content so the public site renders on a fresh DB.
Safe to re-run — all creates use get_or_create keyed on slugs/unique fields.

Demo coach users:
  - email: demo.coach.N@vagus.local (not real email addresses)
  - password: unusable (set_unusable_password)
  - is_active: False (cannot log in)
  - role: 'coach', is_approved: True
  - CoachProfile.is_public: True (so they appear on /koclar/)

No CoachStudent rows are created.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


FEATURE_ITEMS = [
    {
        'slug': 'deneme-analizi',
        'order': 1,
        'title': 'Deneme Analizi',
        'subtitle': 'Net, doğruluk, süre — tek bakışta tüm tablo.',
        'body': (
            'Her deneme sonucunu gir; sistem TYT/AYT net puanlarını, konu bazlı doğruluk oranını '
            've çalışma süresi trendlerini otomatik hesaplar. Hangi konunun seni en çok '
            'düşürdüğünü ve nerede zaman kaybettiğini görmek artık 2 dakika alıyor.'
        ),
        'accent': 'indigo',
        'show_on_home': True,
    },
    {
        'slug': 'aylik-yol-haritasi',
        'order': 2,
        'title': 'Aylık Yol Haritası',
        'subtitle': "YKS'ye kaç ay kaldığını bilen bir plan.",
        'body': (
            'Sınav tarihine göre konu havuzunu aylara böl. Vagus, bitirilmesi gereken '
            'konuları öncelik sırasıyla listeler ve her aya dengeli bir yük dağıtır. '
            'Plan ilerledikçe güncel kalır; geride kalan konular otomatik taşınır.'
        ),
        'accent': 'violet',
        'show_on_home': True,
    },
    {
        'slug': 'haftalik-gorevler',
        'order': 3,
        'title': 'Haftalık Görevler',
        'subtitle': 'Pazartesi sabahı ne yapacağını bil.',
        'body': (
            'Aylık plandan otomatik türetilen haftalık görev listesi, bu haftanın '
            'önceliklerini sıralı gösterir. Görevi tamamladıkça çizgi çek, '
            'tamamlanamayan görevler bir sonraki haftaya taşınır.'
        ),
        'accent': 'emerald',
        'show_on_home': True,
    },
    {
        'slug': 'akilli-katmanlar',
        'order': 4,
        'title': 'Akıllı Katmanlar',
        'subtitle': 'TYT temel, AYT derinlik — ikisi aynı anda.',
        'body': (
            'TYT sağlamlaştırma ve AYT konu çalışması paralel yürüsün. '
            'Vagus iki hedefi aynı anda dengeli şekilde planlar; '
            "TYT'de kayıp vermeden AYT derinliğini artırırsın."
        ),
        'accent': 'amber',
        'show_on_home': True,
    },
    {
        'slug': 'gelisim-grafikleri',
        'order': 5,
        'title': 'Gelişim Grafikleri',
        'subtitle': 'İlerlemeyi sayıyla gör, motivasyonu koru.',
        'body': (
            'Haftalık net değişimi, tamamlanan görev yüzdesini ve konu doğruluk '
            'trendlerini görsel grafiklerle izle. Veli ve koç erişimi sayesinde '
            'aile aynı anda öğrencinin ilerlemesini takip edebilir.'
        ),
        'accent': 'indigo',
        'show_on_home': True,
    },
    {
        'slug': 'veli-takibi',
        'order': 6,
        'title': 'Veli Takibi',
        'subtitle': 'Ebeveynler endişe değil — ilerleme izlesin.',
        'body': (
            'Veliler ayrı bir görünüm üzerinden öğrencinin haftalık ilerleme raporunu, '
            'tamamlanan görevleri ve net trendini takip edebilir. '
            'Bilgi akışı tek yönlü; öğrenci verisine dokunulamaz.'
        ),
        'accent': 'violet',
        'show_on_home': False,
    },
]

PRICING_PLANS = [
    {
        'slug': 'aylik',
        'order': 1,
        'name': 'Aylık',
        'badge_label': '',
        'is_featured': False,
        'price_monthly_try': 149,
        'subtitle': 'Aydan aya esneklik',
        'summary': 'İstediğin zaman iptal et',
        'cta_label': 'Hemen Başla',
        'cta_url': '/auth/register/',
        'features': [
            'Tüm özellikler dahil',
            'Sınırsız deneme analizi',
            'Mobil + masaüstü',
        ],
    },
    {
        'slug': 'donemlik',
        'order': 2,
        'name': 'Dönemlik · 6 Ay',
        'badge_label': '★ En Çok Tercih Edilen',
        'is_featured': True,
        'price_monthly_try': 99,
        'subtitle': 'Bir yarıyıl kapsama',
        'summary': 'Toplam ₺594 — 1 ay hediye · %33 indirim',
        'cta_label': 'Hemen Başla',
        'cta_url': '/auth/register/',
        'features': [
            'Aylık planın tüm özellikleri',
            '1 ay hediye',
            '%100 para iadesi garantisi (ilk 30 gün)',
        ],
    },
    {
        'slug': 'yillik',
        'order': 3,
        'name': 'YKS Yıllık',
        'badge_label': '',
        'is_featured': False,
        'price_monthly_try': 79,
        'subtitle': 'Hazırlığın baştan sona',
        'summary': 'Toplam ₺948 — 4 ay hediye · %47 indirim',
        'cta_label': 'Hemen Başla',
        'cta_url': '/auth/register/',
        'features': [
            'Dönemlik planın tüm özellikleri',
            '4 ay hediye',
            'Birebir uzman görüşmesi (ayda 1)',
        ],
    },
]

FAQ_ITEMS = [
    # Student
    {
        'order': 1, 'category': 'student',
        'question': 'Deneme döneminde ne yapabilirim?',
        'answer': (
            'Tüm özellikler — Dönemlik plan dahil. Sınırsız deneme analizi, '
            'aylık plan, haftalık görevler. Kredi kartı gerekmez.'
        ),
    },
    {
        'order': 2, 'category': 'student',
        'question': 'Deneme sonuçlarımı nasıl gireceğim?',
        'answer': (
            'Panelden "Deneme Ekle" düğmesiyle TYT/AYT net değerlerini, doğru-yanlış '
            'sayılarını ve konu bazlı yanıtlarını girebilirsin. Sistem puanı ve '
            'yüzdelik dilimi otomatik hesaplar.'
        ),
    },
    {
        'order': 3, 'category': 'student',
        'question': 'Plan otomatik mi oluşturuluyor?',
        'answer': (
            'Evet. Sınav tarihini, hedefini ve şu anki seviyeni girdikten sonra '
            'sistem konu havuzunu aylara böler. İstersen planı elle düzenleyebilirsin.'
        ),
    },
    {
        'order': 4, 'category': 'student',
        'question': 'Koç olmadan da kullanabilir miyim?',
        'answer': (
            'Kesinlikle. Vagus koçsuz da tam işlevlidir. Koç, platformun üstüne '
            'ekstra rehberlik katmanı ekler; ama plan, analiz ve görev sistemi '
            'koçsuz da aynı şekilde çalışır.'
        ),
    },
    {
        'order': 5, 'category': 'student',
        'question': 'Aboneliği istediğim zaman iptal edebilir miyim?',
        'answer': (
            'Evet. Aylık planda herhangi bir gün iptal edebilirsin, dönem sonunda '
            'yenileme yapılmaz. Dönemlik ve yıllık planlarda ise ilk 30 gün içinde '
            'tam para iadesi alırsın.'
        ),
    },
    # Parent
    {
        'order': 6, 'category': 'parent',
        'question': 'Vagus, koç/dershane yerine geçer mi?',
        'answer': (
            'Tek başına da etkili — ama Vagus en iyi sonucu koç/dershane ile '
            'birlikte verir. Vagus, öğrencinin planlama ve analiz yükünü üstlenir; '
            'koç veya dershane ise konu anlatımını ve psikolojik desteği sağlar.'
        ),
    },
    {
        'order': 7, 'category': 'parent',
        'question': 'Çocuğumun verilerine ben de bakabilir miyim?',
        'answer': (
            'Evet. Veli hesabıyla öğrencinin haftalık ilerleme raporunu, tamamlanan '
            'görevleri ve net trendini görüntüleyebilirsin. Öğrencinin planına veya '
            'verilerine değişiklik yapamazsın.'
        ),
    },
    {
        'order': 8, 'category': 'parent',
        'question': 'Ödeme güvenli mi?',
        'answer': (
            'Evet. SSL 256-bit şifreleme, PCI-DSS uyumlu ödeme altyapısı ve '
            'Türkiye\'de yerleşik veri merkezleri kullanıyoruz. KVKK kapsamındaki '
            'tüm yükümlülükleri yerine getiriyoruz.'
        ),
    },
]

TESTIMONIALS = [
    {
        'order': 1,
        'student_name': 'Elif K.',
        'initials': 'EK',
        'accent': 'violet-indigo',
        'quote': (
            '"Vagus olmadan TYT planımı hiç bu kadar sistematik yapamıyordum. '
            'Her hafta ne yapacağımı bilmek motivasyonumu ikiye katladı."'
        ),
        'student_info': '12. Sınıf · Sayısal · İstanbul',
    },
    {
        'order': 2,
        'student_name': 'Mert A.',
        'initials': 'MA',
        'accent': 'emerald',
        'quote': (
            '"Net\'im 4 ayda 78\'den 96\'ya çıktı. Vagus\'un her hafta verdiği '
            'listeyi tamamladım, başka bir şey yapmadım."'
        ),
        'student_info': '12. Sınıf · Eşit Ağırlık · Ankara',
    },
    {
        'order': 3,
        'student_name': 'Zeynep D.',
        'initials': 'ZD',
        'accent': 'amber',
        'quote': (
            '"Koçum Vagus\'u takip ederek haftalık görevlerimi veriyor. '
            'Gereksiz çalışmayı sıfırladım, doğru konulara odaklandım."'
        ),
        'student_info': 'Mezun · Sözel · İzmir',
    },
]

DEMO_COACHES = [
    {
        'email': 'demo.coach.1@vagus.local',
        'full_name': 'Demo Koç · Matematik',
        'slug': 'demo-matematik-kocu',
        'display_name': 'Ahmet Yılmaz',
        'title': 'Matematik Koçu',
        'specialty': 'Sayısal · TYT & AYT Matematik',
        'bio_short': (
            'TYT ve AYT matematikte uzmanlaşmış, 8 yıllık YKS koçu. '
            'Öğrencilerinin konu başına doğruluk oranını takip ederek '
            'zayıf noktaları hızla kapatır.'
        ),
        'bio_long': (
            'Ahmet Yılmaz, 8 yıldır YKS matematiği alanında koçluk yapıyor. '
            'ODTÜ Matematik mezunu olan Ahmet, TYT ve AYT matematik müfredatını '
            'derinlemesine biliyor.\n\n'
            'Yaklaşımı veriye dayalı: her öğrenci için konu bazlı doğruluk haritası '
            'çıkarır ve önce en düşük performanslı konuları kapatır. '
            'Ortalama net artışı 4 ayda +15.\n\n'
            'Vagus ile çalışan öğrencilerinde haftalık görev tamamlama oranı %87\'ye ulaştı.'
        ),
        'accent': 'indigo',
        'years_experience': 8,
        'student_count': 180,
        'success_metric': '+15 net / 4 ay',
    },
    {
        'email': 'demo.coach.2@vagus.local',
        'full_name': 'Demo Koç · Türkçe & Edebiyat',
        'slug': 'demo-turkce-kocu',
        'display_name': 'Seda Çelik',
        'title': 'Türkçe & Edebiyat Koçu',
        'specialty': 'Sözel & Eşit Ağırlık · TYT Türkçe · AYT Edebiyat',
        'bio_short': (
            'Sözel ve EA alanı öğrencilerine yönelik TYT Türkçe ve AYT Edebiyat '
            'uzmanlığı. Metni hızlı çözme ve paragraf sorusu stratejileriyle tanınır.'
        ),
        'bio_long': (
            'Seda Çelik, 6 yıldır Türkçe ve edebiyat alanında YKS koçluğu yapıyor. '
            'Hacettepe Türk Dili ve Edebiyatı mezunu olan Seda, '
            'paragraf sorularındaki strateji boşluklarını hızla kapatan yaklaşımıyla öne çıkıyor.\n\n'
            "Özellikle EA ve Sözel alanındaki öğrencilerin TYT Türkçe'de taşıma sürecini "
            'hızlandırıyor. 6 ayda ortalama +10 TYT Türkçe net artışı sağlıyor.'
        ),
        'accent': 'violet',
        'years_experience': 6,
        'student_count': 140,
        'success_metric': '+10 net / 6 ay',
    },
    {
        'email': 'demo.coach.3@vagus.local',
        'full_name': 'Demo Koç · Fen Bilimleri',
        'slug': 'demo-fen-kocu',
        'display_name': 'Can Arslan',
        'title': 'Fen Bilimleri Koçu',
        'specialty': 'Sayısal · AYT Fizik & Kimya',
        'bio_short': (
            "AYT Fizik ve Kimya'da uzmanlaşmış, deneme analizine dayalı "
            'çalışma yöntemiyle kısa sürede net artışı sağlar.'
        ),
        'bio_long': (
            'Can Arslan, İTÜ Fizik Mühendisliği mezunu, 5 yıldır AYT fen bilimleri '
            'alanında koçluk yapıyor.\n\n'
            'Deneme sonuçlarını konu ve kazanım bazlı analiz ederek '
            'her öğrenciye özel çalışma listesi oluşturuyor. '
            "Fizik ve Kimya'yı birlikte planlayan yaklaşımı sayesinde "
            'öğrenciler her iki derste de dengeli ilerleme kaydediyor.\n\n'
            'Ortalama 5 ayda AYT Fizik + Kimya toplam net artışı: +18.'
        ),
        'accent': 'emerald',
        'years_experience': 5,
        'student_count': 110,
        'success_metric': '+18 net (Fiz+Kim)',
    },
]


class Command(BaseCommand):
    help = 'Seed demo marketing content (feature items, pricing, FAQ, testimonials, demo coaches).'

    def handle(self, *args, **options):
        from marketing_app.models import (
            FeatureItem, PricingPlan, PricingFeature, FAQItem, Testimonial, CoachProfile
        )

        # Feature items
        for data in FEATURE_ITEMS:
            obj, created = FeatureItem.objects.get_or_create(
                slug=data['slug'],
                defaults={k: v for k, v in data.items() if k != 'slug'},
            )
            self.stdout.write(f"  FeatureItem '{data['slug']}': {'created' if created else 'skipped'}")

        # Pricing plans + features
        for plan_data in PRICING_PLANS:
            feature_texts = plan_data.pop('features')
            plan, created = PricingPlan.objects.get_or_create(
                slug=plan_data['slug'],
                defaults={k: v for k, v in plan_data.items() if k != 'slug'},
            )
            self.stdout.write(f"  PricingPlan '{plan_data['slug']}': {'created' if created else 'skipped'}")
            if created:
                for i, text in enumerate(feature_texts, start=1):
                    PricingFeature.objects.create(plan=plan, order=i, text=text)
            plan_data['features'] = feature_texts  # restore for idempotency

        # FAQ items
        for data in FAQ_ITEMS:
            obj, created = FAQItem.objects.get_or_create(
                category=data['category'],
                question=data['question'],
                defaults={k: v for k, v in data.items() if k not in ('category', 'question')},
            )
            self.stdout.write(f"  FAQItem '{data['question'][:40]}': {'created' if created else 'skipped'}")

        # Testimonials
        for data in TESTIMONIALS:
            obj, created = Testimonial.objects.get_or_create(
                student_name=data['student_name'],
                defaults={k: v for k, v in data.items() if k != 'student_name'},
            )
            self.stdout.write(f"  Testimonial '{data['student_name']}': {'created' if created else 'skipped'}")

        # Demo coach users + profiles
        for coach_data in DEMO_COACHES:
            email = coach_data['email']
            user, user_created = User.objects.get_or_create(
                email=email,
                defaults={
                    'full_name': coach_data['full_name'],
                    'role': 'coach',
                    'is_approved': True,
                    'is_active': False,
                },
            )
            if user_created:
                user.set_unusable_password()
                user.save()
            self.stdout.write(f"  User '{email}': {'created' if user_created else 'skipped'}")

            profile, profile_created = CoachProfile.objects.get_or_create(
                slug=coach_data['slug'],
                defaults={
                    'user': user,
                    'display_name': coach_data['display_name'],
                    'title': coach_data['title'],
                    'specialty': coach_data['specialty'],
                    'bio_short': coach_data['bio_short'],
                    'bio_long': coach_data['bio_long'],
                    'accent': coach_data['accent'],
                    'years_experience': coach_data['years_experience'],
                    'student_count': coach_data['student_count'],
                    'success_metric': coach_data['success_metric'],
                    'is_public': True,
                    'order': DEMO_COACHES.index(coach_data) + 1,
                },
            )
            self.stdout.write(f"  CoachProfile '{coach_data['slug']}': {'created' if profile_created else 'skipped'}")

        self.stdout.write(self.style.SUCCESS('seed_marketing done.'))

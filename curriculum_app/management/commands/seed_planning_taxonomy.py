"""
Idempotent seed command: sets is_baglayici, yield_score, priority_tag, and
depends_on chains on exams_app.Topic rows according to YKS doctrine.

Run with:
    python manage.py seed_planning_taxonomy
"""
from django.core.management.base import BaseCommand
from exams_app.models import Topic


# ── Low-yield topic name fragments (partial, case-insensitive) ────────────────
LOW_YIELD_FRAGMENTS = [
    'optik', 'dalgalar', 'kaldırma kuvveti', 'akışkanlar', 'elektromanyetik dalga',
]

# ── Bağlayıcı topic definitions per subject name → topic name list ────────────
BAGLAYICI = {
    # TYT Matematik: first 12 gateway topics
    'TYT Matematik': [
        'Temel Kavramlar', 'Sayı Basamakları', 'Bölme ve Bölünebilme', 'EBOB - EKOK',
        'Rasyonel Sayılar', 'Basit Eşitsizlikler', 'Üslü Sayılar', 'Köklü Sayılar',
        'Çarpanlara Ayırma', 'Denklem Çözme', 'Oran Orantı', 'Mutlak Değer',
    ],
    # TYT Geometri: shape foundations that unlock all later geometry
    'TYT Geometri': [
        'Doğru ve Açı', 'Üçgenler',
    ],
    # TYT Fizik
    'TYT Fizik': [
        'Fizik Bilimine Giriş', 'Madde ve Özellikleri', 'Hareket ve Kuvvet',
    ],
    # TYT Kimya
    'TYT Kimya': [
        'Kimya Bilimi', 'Atomun Yapısı', 'Periyodik Sistem',
        'Kimyasal Türler Arası Etkileşimler', 'Maddenin Halleri',
    ],
    # TYT Türkçe: comprehension skills that appear in every exam
    'TYT Türkçe': [
        'Sözcükte Anlam', 'Cümlede Anlam', 'Paragrafta Konu - Ana Düşünce',
    ],
    # TYT Biyoloji: cell foundations unlock almost everything else
    'TYT Biyoloji': [
        'Hücre ve Organelleri', 'Canlıların Sınıflandırılması',
    ],
}

# ── Simple linear prerequisite chains (subject → ordered topic list) ─────────
# depends_on is set: each topic depends on the one before it in the chain.
PREREQ_CHAINS = {
    'TYT Matematik': [
        'Temel Kavramlar', 'Sayı Basamakları', 'Rasyonel Sayılar', 'Üslü Sayılar',
        'Köklü Sayılar', 'Çarpanlara Ayırma', 'Denklem Çözme', 'Basit Eşitsizlikler',
    ],
    'AYT Matematik': [
        'Polinomlar', 'Denklemler ve Eşitsizlikler', 'Fonksiyonlar',
        'Trigonometri', 'Türev', 'İntegral',
    ],
    # AYT Fizik: mechanics chain in doctrine-specified order
    'AYT Fizik': [
        'Vektörler', "Newton'un Hareket Yasaları",
        'Bir Boyutlu Hareket', 'İki Boyutlu Hareket',
        'İş, Güç ve Enerji', 'İtme ve Momentum',
    ],
    # AYT Kimya: equilibrium cluster (logical grouping, not strict prereqs)
    'AYT Kimya': [
        'Kimyasal Tepkimelerde Denge', 'Asit-Baz Dengesi',
        'Çözünürlük Dengesi', 'Kimya ve Elektrik',
    ],
    # AYT Biyoloji: systems chain
    'AYT Biyoloji': [
        'Sinir Sistemi', 'Endokrin Sistem', 'Duyu Organları',
    ],
    # TYT Geometri: shape complexity ramp
    'TYT Geometri': [
        'Doğru ve Açı', 'Üçgenler', 'Dik Üçgen ve Özel Üçgenler',
        'Dörtgenler', 'Çember ve Daire', 'Analitik Geometri — Doğru',
        'Analitik Geometri — Çember', 'Katı Cisimler',
    ],
}


class Command(BaseCommand):
    help = 'Seed curriculum planning metadata on Topic (idempotent).'

    def handle(self, *args, **options):
        self._seed_baglayici()
        self._seed_low_yield()
        self._seed_prereq_chains()
        self.stdout.write(self.style.SUCCESS('seed_planning_taxonomy complete.'))

    def _seed_baglayici(self):
        count = 0
        for subject_name, topic_names in BAGLAYICI.items():
            for name in topic_names:
                updated = Topic.objects.filter(
                    subject__name=subject_name, name=name, is_baglayici=False,
                ).update(is_baglayici=True, priority_tag='CORE')
                count += updated
        self.stdout.write(f'  is_baglayici: {count} topics updated')

    def _seed_low_yield(self):
        count = 0
        for fragment in LOW_YIELD_FRAGMENTS:
            updated = Topic.objects.filter(
                name__icontains=fragment,
            ).exclude(yield_score__lt=40).update(yield_score=25, priority_tag='OPTIONAL')
            count += updated
        self.stdout.write(f'  low yield_score: {count} topics updated')

    def _seed_prereq_chains(self):
        count = 0
        for subject_name, chain in PREREQ_CHAINS.items():
            topics_by_name = {
                t.name: t
                for t in Topic.objects.filter(
                    subject__name=subject_name, name__in=chain,
                )
            }
            for i in range(1, len(chain)):
                pre_name = chain[i - 1]
                cur_name = chain[i]
                pre = topics_by_name.get(pre_name)
                cur = topics_by_name.get(cur_name)
                if pre and cur:
                    cur.depends_on.add(pre)
                    count += 1
        self.stdout.write(f'  depends_on links: {count} set')

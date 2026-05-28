"""
set_tyt_order — assigns pedagogical order_index to TYT topics.

Matching strategy (per entry):
  1. Exact name match.
  2. Prefix match: DB topic name starts with the canonical name.
  3. Explicit override dict (handles renamed / consolidated / split topics).

Topics without any match keep order_index = 9999 (appear at end of pool).
This command is idempotent — safe to re-run.
"""
from django.core.management.base import BaseCommand
from exams_app.models import Subject, Topic

# ── Pedagogical order ───────────────────────────────────────────────────────
# (subject_db_name, canonical_name, order_index)
TYT_ORDER = [
    # ── Türkçe ──────────────────────────────────────────────────────────────
    ('TYT Türkçe', 'Ses Bilgisi',           1),
    ('TYT Türkçe', 'Dil Bilgisi',           2),
    ('TYT Türkçe', 'Noktalama İşaretleri',  3),
    ('TYT Türkçe', 'Yazım Kuralları',       4),
    ('TYT Türkçe', 'Anlatım Bozukluğu',    5),
    ('TYT Türkçe', 'Paragraf',              6),
    ('TYT Türkçe', 'Cümlede Anlam',         7),
    ('TYT Türkçe', 'Sözcükte Anlam',        8),

    # ── Tarih ───────────────────────────────────────────────────────────────
    ('TYT Tarih', 'Tarih ve Zaman',                       1),
    ('TYT Tarih', 'İlk ve Orta Çağlarda Türk Dünyası',   2),
    ('TYT Tarih', 'İslam Medeniyetinin Doğuşu',           3),
    ('TYT Tarih', 'İlk Türk İslam Devletleri',            4),
    ('TYT Tarih', 'Beylikten Devlete Osmanlı',             5),
    ('TYT Tarih', 'Dünya Gücü Osmanlı',                   6),
    ('TYT Tarih', 'Değişim Çağında Avrupa ve Osmanlı',    7),
    ('TYT Tarih', 'Uluslararası İlişkiler 1774-1914',     8),
    ('TYT Tarih', 'XX. Yüzyılda Osmanlı Devleti',         9),
    ('TYT Tarih', 'Milli Mücadele',                       10),
    ('TYT Tarih', 'Atatürkçülük ve Türk İnkılabı',       11),

    # ── Coğrafya ────────────────────────────────────────────────────────────
    ('TYT Coğrafya', 'Doğa ve İnsan',                    1),
    ('TYT Coğrafya', "Dünya'nın Şekli ve Hareketleri",   2),
    ('TYT Coğrafya', 'Coğrafi Konum',                    3),
    ('TYT Coğrafya', 'Harita Bilgisi',                   4),
    ('TYT Coğrafya', 'İklim Bilgisi',                    5),
    ('TYT Coğrafya', 'İç ve Dış Kuvvetler',              6),
    ('TYT Coğrafya', 'Nüfus ve Yerleşme',                7),
    ('TYT Coğrafya', "Türkiye'nin Yer Şekilleri",        8),
    ('TYT Coğrafya', 'Ekonomik Faaliyetler',              9),
    ('TYT Coğrafya', 'Bölgeler',                          10),
    ('TYT Coğrafya', 'Uluslararası Ulaşım Hatları',       11),
    ('TYT Coğrafya', 'Doğal Afetler',                    12),

    # ── Felsefe ─────────────────────────────────────────────────────────────
    ('TYT Felsefe', "Felsefe'nin Konusu", 1),
    ('TYT Felsefe', 'Bilgi Felsefesi',    2),
    ('TYT Felsefe', 'Bilim Felsefesi',    3),
    ('TYT Felsefe', 'Varlık Felsefesi',   4),
    ('TYT Felsefe', 'Ahlak Felsefesi',    5),
    ('TYT Felsefe', 'Siyaset Felsefesi',  6),
    ('TYT Felsefe', 'Din Felsefesi',      7),
    ('TYT Felsefe', 'Sanat Felsefesi',    8),

    # ── Din Kültürü ─────────────────────────────────────────────────────────
    ('TYT Din Kültürü', 'Bilgi ve İnanç',                    1),
    ('TYT Din Kültürü', 'İbadetler',                         2),
    ('TYT Din Kültürü', 'Ahlak ve Değerler',                 3),
    ('TYT Din Kültürü', 'Hz. Muhammed S.A.V',                4),
    ('TYT Din Kültürü', 'Vahiy ve Akıl',                     5),
    ('TYT Din Kültürü', 'İslam Düşüncesinde Yorumlar',       6),
    ('TYT Din Kültürü', 'Din, Kültür ve Medeniyet',          7),

    # ── Matematik ───────────────────────────────────────────────────────────
    ('TYT Matematik', 'Temel Kavramlar',        1),
    ('TYT Matematik', 'Sayı Basamakları',        2),
    ('TYT Matematik', 'Bölünebilme Kuralları',   3),
    ('TYT Matematik', 'OBEB-OKEK',               4),
    ('TYT Matematik', 'Rasyonel Sayılar',        5),
    ('TYT Matematik', 'Basit Eşitsizlikler',     6),
    ('TYT Matematik', 'Mutlak Değer',            7),
    ('TYT Matematik', 'Üslü Sayılar',            8),
    ('TYT Matematik', 'Köklü Sayılar',           9),
    ('TYT Matematik', 'Çarpanlara Ayırma',       10),
    ('TYT Matematik', 'Oran - Orantı',           11),
    ('TYT Matematik', 'Denklem Çözme',           12),
    ('TYT Matematik', 'Problemler',              13),
    ('TYT Matematik', 'Kümeler / Kartezyen',     14),
    ('TYT Matematik', 'Mantık',                  15),
    ('TYT Matematik', 'Fonksiyonlar',            16),
    ('TYT Matematik', 'Polinomlar',              17),
    ('TYT Matematik', 'Permütasyon - Kombinasyon', 18),
    ('TYT Matematik', 'Olasılık',               19),
    ('TYT Matematik', 'Veri - İstatistik',       20),

    # ── Geometri ────────────────────────────────────────────────────────────
    ('TYT Geometri', 'Açılar ve Üçgenler',  1),
    ('TYT Geometri', 'Çokgenler',           2),
    ('TYT Geometri', 'Yamuk',               3),
    ('TYT Geometri', 'Eşkenar Dörtgen',     4),
    ('TYT Geometri', 'Deltoid',             5),
    ('TYT Geometri', 'Kare',               6),
    ('TYT Geometri', 'Dikdörtgen',         7),
    ('TYT Geometri', 'Çember ve Daire',    8),
    ('TYT Geometri', 'Analitik Geometri',  9),
    ('TYT Geometri', 'Katı Cisimler',      10),

    # ── Fizik ───────────────────────────────────────────────────────────────
    ('TYT Fizik', 'Fizik Bilimine Giriş',        1),
    ('TYT Fizik', 'Madde ve Özellikleri',         2),
    ('TYT Fizik', 'Sıvıların Kaldırma Kuvveti',  3),
    ('TYT Fizik', 'Basınç',                       4),
    ('TYT Fizik', 'Isı, Sıcaklık ve Genleşme',   5),
    ('TYT Fizik', 'Hareket ve Kuvvet',            6),
    ('TYT Fizik', 'Dinamik',                      7),
    ('TYT Fizik', 'İş, Güç ve Enerji',            8),
    ('TYT Fizik', 'Elektrostatik',                9),
    ('TYT Fizik', 'Elektrik Akımı ve Devreler',  10),
    ('TYT Fizik', 'Elektriksel Enerji ve Güç',   11),
    ('TYT Fizik', 'Optik',                        12),
    ('TYT Fizik', 'Manyetizma',                   13),
    ('TYT Fizik', 'Dalgalar',                     14),

    # ── Kimya ───────────────────────────────────────────────────────────────
    ('TYT Kimya', 'Kimya Bilimi',                         1),
    ('TYT Kimya', 'Atomun Yapısı',                        2),
    ('TYT Kimya', 'Periyodik Tablo',                      3),
    ('TYT Kimya', 'Maddenin Halleri',                     4),
    ('TYT Kimya', 'Kimyasal Türler Arası Etkileşimler',  5),
    ('TYT Kimya', 'Kimyasal Hesaplamalar',                6),
    ('TYT Kimya', 'Kimyanın Temel Kanunları',             7),
    ('TYT Kimya', 'Asit, Baz ve Tuz',                    8),
    ('TYT Kimya', 'Karışımlar',                           9),
    ('TYT Kimya', 'Kimya Her Yerde',                      10),

    # ── Biyoloji ────────────────────────────────────────────────────────────
    ('TYT Biyoloji', 'Canlıların Ortak Özellikleri',   1),
    ('TYT Biyoloji', 'Canlıların Temel Bileşenleri',   2),
    ('TYT Biyoloji', 'Hücre ve Organelleri',           3),
    ('TYT Biyoloji', 'Hücre Zarından Madde Geçişi',   4),
    ('TYT Biyoloji', 'Canlıların Sınıflandırılması',  5),
    ('TYT Biyoloji', 'Hücre Bölünmeleri ve Üreme',    6),
    ('TYT Biyoloji', 'Kalıtım',                        7),
    ('TYT Biyoloji', 'Ekosistem Ekoloji',              8),
    ('TYT Biyoloji', 'Güncel Çevre Sorunları',         9),
]

# ── Explicit overrides ───────────────────────────────────────────────────────
# Maps (subject_db_name, canonical_name) → list of exact DB topic names.
# Used when exact or prefix match would fail or produce wrong results.
# Empty list [] means "this canonical name has no DB counterpart — will be reported."
EXPLICIT_OVERRIDES = {
    # Türkçe
    ('TYT Türkçe', 'Paragraf'): [
        'Paragrafta Anlatım Teknikleri',
        'Paragrafta Düşünceyi Geliştirme Yolları',
        'Paragrafta Yapı',
        'Paragrafta Konu - Ana Düşünce',
        'Paragrafta Yardımcı Düşünce',
    ],
    # Tarih
    ('TYT Tarih', 'İslam Medeniyetinin Doğuşu'): [
        'İslam Medeniyetinin Doğuşu ve İlk İslam Devletleri',
    ],
    ('TYT Tarih', 'İlk Türk İslam Devletleri'): [
        "Türklerin İslamiyet'i Kabulü ve İlk Türk İslam Devletleri",
    ],
    ('TYT Tarih', 'Beylikten Devlete Osmanlı'): [
        'Beylikten Devlete Osmanlı Siyaseti',
        'Beylikten Devlete Osmanlı Medeniyeti',
    ],
    ('TYT Tarih', 'Uluslararası İlişkiler 1774-1914'): [
        'Uluslararası İlişkilerde Denge Stratejisi (1774-1914)',
    ],
    ('TYT Tarih', 'XX. Yüzyılda Osmanlı Devleti'): [
        'XX. Yüzyıl Başlarında Osmanlı Devleti ve Dünya',
    ],
    # Coğrafya
    ('TYT Coğrafya', 'İç ve Dış Kuvvetler'): [
        'İç Kuvvetler / Dış Kuvvetler',
    ],
    ('TYT Coğrafya', 'Nüfus ve Yerleşme'): [
        'Nüfus',
        "Türkiye'de Nüfus",
        'Göç',
    ],
    # Felsefe
    ('TYT Felsefe', "Felsefe'nin Konusu"): [
        'Felsefenin Konusu',
    ],
    # Din Kültürü
    ('TYT Din Kültürü', 'İbadetler'): [
        'İslam ve İbadet',
    ],
    ('TYT Din Kültürü', 'Ahlak ve Değerler'): [
        'Gençlik ve Değerler',
    ],
    ('TYT Din Kültürü', 'Hz. Muhammed S.A.V'): [
        'Bir Genç Olarak Hz. Muhammed',
        'Hz. Muhammed ve Gençler',
    ],
    ('TYT Din Kültürü', 'Vahiy ve Akıl'): [],       # Not in DB — will be reported
    ('TYT Din Kültürü', 'İslam Düşüncesinde Yorumlar'): [
        'İslam Düşüncesinde İtikadi ve Siyasi Yorumlar',
        'İslam Düşüncesinde Fıkhi Yorumlar',
    ],
    ('TYT Din Kültürü', 'Din, Kültür ve Medeniyet'): [
        'Din, Kültür ve Sanat',
    ],
    # Matematik
    ('TYT Matematik', 'Bölünebilme Kuralları'): ['Bölme ve Bölünebilme'],
    ('TYT Matematik', 'OBEB-OKEK'):             ['EBOB - EKOK'],
    ('TYT Matematik', 'Oran - Orantı'):         ['Oran Orantı'],
    ('TYT Matematik', 'Problemler'): [
        'Problemler - Sayı', 'Problemler - Kesir', 'Problemler - Yaş',
        'Problemler - Hareket ve Hız', 'Problemler - İşçi Emek',
        'Problemler - Yüzde', 'Problemler - Kar Zarar',
        'Problemler - Karışım', 'Problemler - Grafik',
        'Problemler - Rutin Olmayan',
    ],
    ('TYT Matematik', 'Kümeler / Kartezyen'): ['Kümeler - Kartezyen Çarpım'],
    ('TYT Matematik', 'Veri - İstatistik'):    ['Veri ve İstatistik'],
    # Geometri
    ('TYT Geometri', 'Açılar ve Üçgenler'): [
        'Doğru ve Açı', 'Üçgenler', 'Dik Üçgen ve Özel Üçgenler',
    ],
    ('TYT Geometri', 'Yamuk'):          [],  # Not in DB
    ('TYT Geometri', 'Eşkenar Dörtgen'): [], # Not in DB
    ('TYT Geometri', 'Deltoid'):        [],  # Not in DB
    ('TYT Geometri', 'Kare'):           [],  # Not in DB
    ('TYT Geometri', 'Dikdörtgen'):     [],  # Not in DB
    ('TYT Geometri', 'Analitik Geometri'): [
        'Analitik Geometri — Doğru',
        'Analitik Geometri — Çember',
    ],
    # Fizik
    ('TYT Fizik', 'Sıvıların Kaldırma Kuvveti'): ['Kaldırma Kuvveti'],
    ('TYT Fizik', 'İş, Güç ve Enerji'): ['İş, Güç ve Enerji I', 'İş, Güç ve Enerji II'],
    ('TYT Fizik', 'Elektrik Akımı ve Devreler'): ['Elektrik ve Manyetizma'],
    ('TYT Fizik', 'Elektriksel Enerji ve Güç'): [],  # Not in DB
    ('TYT Fizik', 'Manyetizma'): [],  # Merged into 'Elektrik ve Manyetizma' above
    # Kimya
    ('TYT Kimya', 'Periyodik Tablo'): ['Periyodik Sistem'],
    # Biyoloji
    ('TYT Biyoloji', 'Hücre Bölünmeleri ve Üreme'): [
        'Mitoz ve Eşeysiz Üreme', 'Mayoz ve Eşeyli Üreme',
    ],
    ('TYT Biyoloji', 'Ekosistem Ekoloji'): ['Ekosistem Ekolojisi'],
}


class Command(BaseCommand):
    help = 'TYT konularına pedagojik order_index atar (idempotent).'

    def handle(self, *args, **options):
        # topic_id → order_index to set
        assignments: dict[int, int] = {}
        not_found: list[str] = []
        matched_count = 0
        db_name_to_id: dict[tuple, int] = {}

        # Pre-load all TYT topics into a dict keyed by (subject_name, topic_name)
        tyt_topics = list(
            Topic.objects.filter(subject__exam_type='TYT')
            .select_related('subject')
        )
        for t in tyt_topics:
            db_name_to_id[(t.subject.name, t.name)] = t.id

        # Group DB topics by subject for prefix matching
        by_subject: dict[str, list[Topic]] = {}
        for t in tyt_topics:
            by_subject.setdefault(t.subject.name, []).append(t)

        # Process each canonical entry
        for subj_name, canonical, idx in TYT_ORDER:
            key = (subj_name, canonical)

            # ── Path A: explicit override ──────────────────────────────────
            if key in EXPLICIT_OVERRIDES:
                db_names = EXPLICIT_OVERRIDES[key]
                if not db_names:
                    not_found.append(f"{subj_name} / [{canonical}] - override=[] (konu DB'de yok)")
                    continue
                found_any = False
                for db_name in db_names:
                    tid = db_name_to_id.get((subj_name, db_name))
                    if tid is not None:
                        assignments[tid] = idx
                        found_any = True
                    else:
                        not_found.append(
                            f"{subj_name} / [{canonical}] -> override [{db_name}] DB'de bulunamadi"
                        )
                if found_any:
                    matched_count += 1
                continue

            # ── Path B: exact match ────────────────────────────────────────
            tid = db_name_to_id.get((subj_name, canonical))
            if tid is not None:
                assignments[tid] = idx
                matched_count += 1
                continue

            # ── Path C: prefix match ───────────────────────────────────────
            prefix_hits = [
                t for t in by_subject.get(subj_name, [])
                if t.name.startswith(canonical)
            ]
            if prefix_hits:
                for t in prefix_hits:
                    assignments[t.id] = idx
                matched_count += 1
                continue

            # ── Path D: no match ───────────────────────────────────────────
            not_found.append(f'{subj_name} / [{canonical}] - eslesme bulunamadi')

        # Bulk update in batches
        total_updated = 0
        ids_to_update = list(assignments.keys())
        # Reset all TYT topics to 9999 first, then apply
        Topic.objects.filter(subject__exam_type='TYT').update(order_index=9999)
        for tid, oidx in assignments.items():
            Topic.objects.filter(id=tid).update(order_index=oidx)
            total_updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'OK: {matched_count} kanonik giris eslendi, {total_updated} konu guncellendi.'
        ))

        if not_found:
            self.stdout.write(self.style.WARNING('\nUYARI - Eslesmeyen / DB de olmayan girisler:'))
            for msg in not_found:
                self.stdout.write(self.style.WARNING(f'  - {msg}'))
        else:
            self.stdout.write(self.style.SUCCESS('Tum girisler eslendi.'))

        self.stdout.write('\nDogrulama:')
        self.stdout.write('  python manage.py shell')
        self.stdout.write('  >>> from exams_app.models import Topic, Subject')
        self.stdout.write("  >>> s = Subject.objects.get(name='TYT Matematik')")
        self.stdout.write("  >>> print([(t.order_index, t.name) for t in s.topics.order_by('order_index', 'name')])")

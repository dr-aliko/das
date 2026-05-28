from django.core.management.base import BaseCommand
from exams_app.models import Publisher, Subject, Topic

PUBLISHERS = [
    '3D Yayınları', 'Limit Yayınları', 'Endemik Yayınları',
    'Bilgi Sarmal', 'Fen Bilimleri Yayınları',
]

# (subject_name, question_count, sub_category, topic_name)
TYT_TOPICS = [
    # ── TÜRKÇE ─────────────────────────────────────────────────────
    ('TYT Türkçe', 40, '', 'Sözcükte Anlam'),
    ('TYT Türkçe', 40, '', 'Söz Yorumu'),
    ('TYT Türkçe', 40, '', 'Deyim ve Atasözü'),
    ('TYT Türkçe', 40, '', 'Cümlede Anlam'),
    ('TYT Türkçe', 40, '', 'Paragrafta Anlatım Teknikleri'),
    ('TYT Türkçe', 40, '', 'Paragrafta Düşünceyi Geliştirme Yolları'),
    ('TYT Türkçe', 40, '', 'Paragrafta Yapı'),
    ('TYT Türkçe', 40, '', 'Paragrafta Konu - Ana Düşünce'),
    ('TYT Türkçe', 40, '', 'Paragrafta Yardımcı Düşünce'),
    ('TYT Türkçe', 40, '', 'Ses Bilgisi'),
    ('TYT Türkçe', 40, '', 'Yazım Kuralları'),
    ('TYT Türkçe', 40, '', 'Noktalama İşaretleri'),
    ('TYT Türkçe', 40, '', 'Sözcükte Yapı/Ekler'),
    ('TYT Türkçe', 40, '', 'Sözcük Türleri - İsimler'),
    ('TYT Türkçe', 40, '', 'Sözcük Türleri - Zamirler'),
    ('TYT Türkçe', 40, '', 'Sözcük Türleri - Sıfatlar'),
    ('TYT Türkçe', 40, '', 'Sözcük Türleri - Zarflar'),
    ('TYT Türkçe', 40, '', 'Sözcük Türleri - Edat, Bağlaç, Ünlem'),
    ('TYT Türkçe', 40, '', 'Fiilde Anlam (Kip - Kişi - Yapı)'),
    ('TYT Türkçe', 40, '', 'Ek Fiil'),
    ('TYT Türkçe', 40, '', 'Fiilimsi'),
    ('TYT Türkçe', 40, '', 'Fiilde Çatı'),
    ('TYT Türkçe', 40, '', 'Sözcük Grupları'),
    ('TYT Türkçe', 40, '', 'Cümlenin Ögeleri'),
    ('TYT Türkçe', 40, '', 'Cümle Türleri'),
    ('TYT Türkçe', 40, '', 'Anlatım Bozukluğu'),

    # ── MATEMATİK ──────────────────────────────────────────────────
    ('TYT Matematik', 40, '', 'Temel Kavramlar'),
    ('TYT Matematik', 40, '', 'Sayı Basamakları'),
    ('TYT Matematik', 40, '', 'Bölme ve Bölünebilme'),
    ('TYT Matematik', 40, '', 'EBOB - EKOK'),
    ('TYT Matematik', 40, '', 'Rasyonel Sayılar'),
    ('TYT Matematik', 40, '', 'Basit Eşitsizlikler'),
    ('TYT Matematik', 40, '', 'Mutlak Değer'),
    ('TYT Matematik', 40, '', 'Üslü Sayılar'),
    ('TYT Matematik', 40, '', 'Köklü Sayılar'),
    ('TYT Matematik', 40, '', 'Çarpanlara Ayırma'),
    ('TYT Matematik', 40, '', 'Oran Orantı'),
    ('TYT Matematik', 40, '', 'Denklem Çözme'),
    ('TYT Matematik', 40, '', 'Problemler - Sayı'),
    ('TYT Matematik', 40, '', 'Problemler - Kesir'),
    ('TYT Matematik', 40, '', 'Problemler - Yaş'),
    ('TYT Matematik', 40, '', 'Problemler - Hareket ve Hız'),
    ('TYT Matematik', 40, '', 'Problemler - İşçi Emek'),
    ('TYT Matematik', 40, '', 'Problemler - Yüzde'),
    ('TYT Matematik', 40, '', 'Problemler - Kar Zarar'),
    ('TYT Matematik', 40, '', 'Problemler - Karışım'),
    ('TYT Matematik', 40, '', 'Problemler - Grafik'),
    ('TYT Matematik', 40, '', 'Problemler - Rutin Olmayan'),
    ('TYT Matematik', 40, '', 'Kümeler - Kartezyen Çarpım'),
    ('TYT Matematik', 40, '', 'Mantık'),
    ('TYT Matematik', 40, '', 'Fonksiyonlar'),
    ('TYT Matematik', 40, '', 'Polinomlar'),
    ('TYT Matematik', 40, '', 'II. Dereceden Denklemler'),
    ('TYT Matematik', 40, '', 'Permütasyon - Kombinasyon'),
    ('TYT Matematik', 40, '', 'Olasılık'),
    ('TYT Matematik', 40, '', 'Veri ve İstatistik'),

    # ── TYT TARİH ──────────────────────────────────────────────────
    ('TYT Tarih', 5, '', 'Tarih ve Zaman'),
    ('TYT Tarih', 5, '', 'İnsanlığın İlk Dönemleri'),
    ('TYT Tarih', 5, '', 'İlk ve Orta Çağlarda Türk Dünyası'),
    ('TYT Tarih', 5, '', 'İslam Medeniyetinin Doğuşu ve İlk İslam Devletleri'),
    ('TYT Tarih', 5, '', "Türklerin İslamiyet'i Kabulü ve İlk Türk İslam Devletleri"),
    ('TYT Tarih', 5, '', "Orta Çağ'da Dünya"),
    ('TYT Tarih', 5, '', "Yerleşme ve Devletleşme Sürecinde Selçuklu Türkiye'si"),
    ('TYT Tarih', 5, '', 'Beylikten Devlete Osmanlı Siyaseti'),
    ('TYT Tarih', 5, '', 'Devletleşme Sürecinde Savaşçılar ve Askerler'),
    ('TYT Tarih', 5, '', 'Beylikten Devlete Osmanlı Medeniyeti'),
    ('TYT Tarih', 5, '', 'Dünya Gücü Osmanlı'),
    ('TYT Tarih', 5, '', 'Sultan ve Osmanlı Merkez Teşkilatı'),
    ('TYT Tarih', 5, '', 'Klasik Çağda Osmanlı Toplum Düzeni'),
    ('TYT Tarih', 5, '', 'Değişen Dünya Dengeleri Karşısında Osmanlı Siyaseti'),
    ('TYT Tarih', 5, '', 'Değişim Çağında Avrupa ve Osmanlı'),
    ('TYT Tarih', 5, '', 'Uluslararası İlişkilerde Denge Stratejisi (1774-1914)'),
    ('TYT Tarih', 5, '', 'Devrimler Çağında Değişen Devlet-Toplum İlişkileri'),
    ('TYT Tarih', 5, '', 'Sermaye ve Emek'),
    ('TYT Tarih', 5, '', 'XIX. ve XX. Yüzyılda Değişen Gündelik Hayat'),
    ('TYT Tarih', 5, '', 'XX. Yüzyıl Başlarında Osmanlı Devleti ve Dünya'),
    ('TYT Tarih', 5, '', 'Milli Mücadele'),
    ('TYT Tarih', 5, '', 'Atatürkçülük ve Türk İnkılabı'),

    # ── TYT COĞRAFYA ───────────────────────────────────────────────
    ('TYT Coğrafya', 5, '', 'Doğa ve İnsan'),
    ('TYT Coğrafya', 5, '', "Dünya'nın Şekli ve Hareketleri"),
    ('TYT Coğrafya', 5, '', 'Coğrafi Konum'),
    ('TYT Coğrafya', 5, '', 'Harita Bilgisi'),
    ('TYT Coğrafya', 5, '', 'İklim Bilgisi'),
    ('TYT Coğrafya', 5, '', "Dünya'nın Tektonik Oluşumu"),
    ('TYT Coğrafya', 5, '', 'Jeolojik Zamanlar'),
    ('TYT Coğrafya', 5, '', 'İç Kuvvetler / Dış Kuvvetler'),
    ('TYT Coğrafya', 5, '', 'Kayaçlar'),
    ('TYT Coğrafya', 5, '', "Türkiye'nin Yer Şekilleri"),
    ('TYT Coğrafya', 5, '', 'Su - Toprak ve Bitkiler'),
    ('TYT Coğrafya', 5, '', 'Nüfus'),
    ('TYT Coğrafya', 5, '', "Türkiye'de Nüfus"),
    ('TYT Coğrafya', 5, '', 'Göç'),
    ('TYT Coğrafya', 5, '', 'Ekonomik Faaliyetler'),
    ('TYT Coğrafya', 5, '', 'Bölgeler'),
    ('TYT Coğrafya', 5, '', 'Uluslararası Ulaşım Hatları'),
    ('TYT Coğrafya', 5, '', 'Çevre ve Toplum'),
    ('TYT Coğrafya', 5, '', 'Doğal Afetler'),

    # ── TYT FELSEFE ────────────────────────────────────────────────
    ('TYT Felsefe', 4, '', 'Felsefenin Konusu'),
    ('TYT Felsefe', 4, '', 'Bilgi Felsefesi'),
    ('TYT Felsefe', 4, '', 'Varlık Felsefesi'),
    ('TYT Felsefe', 4, '', 'Ahlak Felsefesi'),
    ('TYT Felsefe', 4, '', 'Sanat Felsefesi'),
    ('TYT Felsefe', 4, '', 'Din Felsefesi'),
    ('TYT Felsefe', 4, '', 'Siyaset Felsefesi'),
    ('TYT Felsefe', 4, '', 'Bilim Felsefesi'),
    ('TYT Felsefe', 4, '', 'İlk Çağ Felsefesi'),
    ('TYT Felsefe', 4, '', '2. ve 15. Yüzyıl Felsefeleri'),
    ('TYT Felsefe', 4, '', '15. ve 17. Yüzyıl Felsefeleri'),
    ('TYT Felsefe', 4, '', '18. ve 19. Yüzyıl Felsefeleri'),
    ('TYT Felsefe', 4, '', '20. Yüzyıl Felsefesi'),

    # ── TYT DİN KÜLTÜRÜ ────────────────────────────────────────────
    ('TYT Din Kültürü', 4, '', 'Bilgi ve İnanç'),
    ('TYT Din Kültürü', 4, '', 'Din ve İslam'),
    ('TYT Din Kültürü', 4, '', 'İslam ve İbadet'),
    ('TYT Din Kültürü', 4, '', 'Gençlik ve Değerler'),
    ('TYT Din Kültürü', 4, '', 'İslam Medeniyeti ve Özellikleri'),
    ('TYT Din Kültürü', 4, '', 'Allah İnancı ve İnsan'),
    ('TYT Din Kültürü', 4, '', "Allah'ın Varlığı ve Birliği"),
    ('TYT Din Kültürü', 4, '', "Allah'ın İsim ve Sıfatları"),
    ('TYT Din Kültürü', 4, '', "Kur'an-ı Kerim'de İnsan ve Özellikleri"),
    ('TYT Din Kültürü', 4, '', 'İnsanın Allah İle İrtibatı'),
    ('TYT Din Kültürü', 4, '', "Kur'an-ı Kerim'de Gençler"),
    ('TYT Din Kültürü', 4, '', 'Bir Genç Olarak Hz. Muhammed'),
    ('TYT Din Kültürü', 4, '', 'Hz. Muhammed ve Gençler'),
    ('TYT Din Kültürü', 4, '', 'Bazı Genç Sahabeler'),
    ('TYT Din Kültürü', 4, '', 'Din ve Aile'),
    ('TYT Din Kültürü', 4, '', 'Din, Kültür ve Sanat'),
    ('TYT Din Kültürü', 4, '', 'Din ve Çevre'),
    ('TYT Din Kültürü', 4, '', 'Din ve Sosyal Değişim'),
    ('TYT Din Kültürü', 4, '', 'Din ve Ekonomi'),
    ('TYT Din Kültürü', 4, '', 'Din ve Sosyal Adalet'),
    ('TYT Din Kültürü', 4, '', 'İslam Ahlakı'),
    ('TYT Din Kültürü', 4, '', 'Dinî Yorum Farklılıklarının Sebepleri'),
    ('TYT Din Kültürü', 4, '', 'Dinî Yorumlarla İlgili Bazı Kavramlar'),
    ('TYT Din Kültürü', 4, '', 'İslam Düşüncesinde İtikadi ve Siyasi Yorumlar'),
    ('TYT Din Kültürü', 4, '', 'İslam Düşüncesinde Fıkhi Yorumlar'),

    # ── TYT FİZİK (branş, 7 soru) ──────────────────────────────────
    ('TYT Fizik', 7, '', 'Fizik Bilimine Giriş'),
    ('TYT Fizik', 7, '', 'Madde ve Özellikleri'),
    ('TYT Fizik', 7, '', 'Hareket ve Kuvvet'),
    ('TYT Fizik', 7, '', 'İş, Güç ve Enerji I'),
    ('TYT Fizik', 7, '', 'Isı, Sıcaklık ve Genleşme'),
    ('TYT Fizik', 7, '', 'Dinamik'),
    ('TYT Fizik', 7, '', 'İş, Güç ve Enerji II'),
    ('TYT Fizik', 7, '', 'Elektrostatik'),
    ('TYT Fizik', 7, '', 'Elektrik ve Manyetizma'),
    ('TYT Fizik', 7, '', 'Basınç'),
    ('TYT Fizik', 7, '', 'Kaldırma Kuvveti'),
    ('TYT Fizik', 7, '', 'Dalgalar'),
    ('TYT Fizik', 7, '', 'Optik'),

    # ── TYT KİMYA (branş, 7 soru) ──────────────────────────────────
    ('TYT Kimya', 7, '', 'Kimya Bilimi'),
    ('TYT Kimya', 7, '', 'Atomun Yapısı'),
    ('TYT Kimya', 7, '', 'Periyodik Sistem'),
    ('TYT Kimya', 7, '', 'Maddenin Halleri'),
    ('TYT Kimya', 7, '', 'Kimyasal Türler Arası Etkileşimler'),
    ('TYT Kimya', 7, '', 'Kimyasal Hesaplamalar'),
    ('TYT Kimya', 7, '', 'Kimyanın Temel Kanunları'),
    ('TYT Kimya', 7, '', 'Asit, Baz ve Tuz'),
    ('TYT Kimya', 7, '', 'Karışımlar'),
    ('TYT Kimya', 7, '', 'Endüstride ve Canlılarda Enerji'),
    ('TYT Kimya', 7, '', 'Kimya Her Yerde'),

    # ── TYT BİYOLOJİ (branş, 6 soru) ───────────────────────────────
    ('TYT Biyoloji', 6, '', 'Canlıların Ortak Özellikleri'),
    ('TYT Biyoloji', 6, '', 'Canlıların Temel Bileşenleri'),
    ('TYT Biyoloji', 6, '', 'Hücre ve Organelleri'),
    ('TYT Biyoloji', 6, '', 'Hücre Zarından Madde Geçişi'),
    ('TYT Biyoloji', 6, '', 'Canlıların Sınıflandırılması'),
    ('TYT Biyoloji', 6, '', 'Mitoz ve Eşeysiz Üreme'),
    ('TYT Biyoloji', 6, '', 'Mayoz ve Eşeyli Üreme'),
    ('TYT Biyoloji', 6, '', 'Kalıtım'),
    ('TYT Biyoloji', 6, '', 'Ekosistem Ekolojisi'),
    ('TYT Biyoloji', 6, '', 'Güncel Çevre Sorunları'),

    # ── TYT GEOMETRİ ───────────────────────────────────────────────
    ('TYT Geometri', 10, '', 'Doğru ve Açı'),
    ('TYT Geometri', 10, '', 'Üçgenler'),
    ('TYT Geometri', 10, '', 'Dik Üçgen ve Özel Üçgenler'),
    ('TYT Geometri', 10, '', 'Çokgenler'),
    ('TYT Geometri', 10, '', 'Dörtgenler'),
    ('TYT Geometri', 10, '', 'Çember ve Daire'),
    ('TYT Geometri', 10, '', 'Analitik Geometri — Doğru'),
    ('TYT Geometri', 10, '', 'Analitik Geometri — Çember'),
    ('TYT Geometri', 10, '', 'Katı Cisimler'),
    ('TYT Geometri', 10, '', 'Dönüşüm Geometrisi'),
]

# (subject_name, question_count, sub_category, topic_name)
# SAY track only: Matematik, Fizik, Kimya, Biyoloji — 70 topics total
AYT_TOPICS = [
    # ── AYT MATEMATİK (12) ─────────────────────────────────────────
    ('AYT Matematik', 30, '', 'Fonksiyonlar'),
    ('AYT Matematik', 30, '', 'Polinomlar'),
    ('AYT Matematik', 30, '', 'Dereceden Denklemler ve Eşitsizlikler'),
    ('AYT Matematik', 30, '', 'Parabol'),
    ('AYT Matematik', 30, '', 'Permütasyon-Kombinasyon-Olasılık – Binom'),
    ('AYT Matematik', 30, '', 'Trigonometri'),
    ('AYT Matematik', 30, '', 'Karmaşık Sayılar'),
    ('AYT Matematik', 30, '', 'Logaritma'),
    ('AYT Matematik', 30, '', 'Diziler'),
    ('AYT Matematik', 30, '', 'Limit'),
    ('AYT Matematik', 30, '', 'Türev'),
    ('AYT Matematik', 30, '', 'İntegral'),

    # ── AYT FİZİK (26) ─────────────────────────────────────────────
    ('AYT Fizik', 14, '', 'Vektörler'),
    ('AYT Fizik', 14, '', 'Bağıl Hareket'),
    ('AYT Fizik', 14, '', "Newton'un Hareket Yasaları"),
    ('AYT Fizik', 14, '', 'Bir Boyutta Sabit İvmeli Hareket'),
    ('AYT Fizik', 14, '', 'Atışlar'),
    ('AYT Fizik', 14, '', 'İş, Güç ve Enerji'),
    ('AYT Fizik', 14, '', 'İtme ve Momentum'),
    ('AYT Fizik', 14, '', 'Kuvvet, Tork ve Denge'),
    ('AYT Fizik', 14, '', 'Kütle Merkezi'),
    ('AYT Fizik', 14, '', 'Basit Makineler'),
    ('AYT Fizik', 14, '', 'Çembersel Hareket'),
    ('AYT Fizik', 14, '', 'Dönme, Yuvarlanma ve Açısal Momentum'),
    ('AYT Fizik', 14, '', 'Kütle Çekim ve Kepler Yasaları'),
    ('AYT Fizik', 14, '', 'Basit Harmonik Hareket'),
    ('AYT Fizik', 14, '', 'Elektrik Alan ve Potansiyel'),
    ('AYT Fizik', 14, '', 'Paralel Levhalar ve Sığa'),
    ('AYT Fizik', 14, '', 'Manyetik Alan ve Manyetik Kuvvet'),
    ('AYT Fizik', 14, '', 'İndüksiyon, Alternatif Akım ve Transformatörler'),
    ('AYT Fizik', 14, '', 'Dalga Mekaniği ve Elektromanyetik Dalgalar'),
    ('AYT Fizik', 14, '', 'Özel Görelilik'),
    ('AYT Fizik', 14, '', 'Kara Cisim Işıması'),
    ('AYT Fizik', 14, '', 'Fotoelektrik Olay ve Compton Olayı'),
    ('AYT Fizik', 14, '', 'Atom Modelleri'),
    ('AYT Fizik', 14, '', 'Radyoaktivite'),
    ('AYT Fizik', 14, '', 'Büyük Patlama ve Parçacık Fiziği'),
    ('AYT Fizik', 14, '', 'Modern Fiziğin Teknolojideki Uygulamaları'),

    # ── AYT KİMYA (15) ─────────────────────────────────────────────
    ('AYT Kimya', 13, '', 'Kimya Bilimi'),
    ('AYT Kimya', 13, '', 'Atom ve Yapısı'),
    ('AYT Kimya', 13, '', 'Periyodik Sistem'),
    ('AYT Kimya', 13, '', 'Kimyasal Türler Arası Etkileşim'),
    ('AYT Kimya', 13, '', 'Kimyasal Hesaplamalar'),
    ('AYT Kimya', 13, '', 'Modern Atom Teorisi'),
    ('AYT Kimya', 13, '', 'Gazlar'),
    ('AYT Kimya', 13, '', 'Sıvı Çözeltiler'),
    ('AYT Kimya', 13, '', 'Kimyasal Tepkimelerde Enerji'),
    ('AYT Kimya', 13, '', 'Kimyasal Tepkimelerde Hız'),
    ('AYT Kimya', 13, '', 'Kimyasal Tepkimelerde Denge'),
    ('AYT Kimya', 13, '', 'Asit-Baz Dengesi'),
    ('AYT Kimya', 13, '', 'Çözünürlük Dengesi'),
    ('AYT Kimya', 13, '', 'Kimya ve Elektrik'),
    ('AYT Kimya', 13, '', 'Organik Kimya'),

    # ── AYT BİYOLOJİ (17) ──────────────────────────────────────────
    ('AYT Biyoloji', 13, '', 'Canlılık ve Enerji'),
    ('AYT Biyoloji', 13, '', 'Nükleik Asitler'),
    ('AYT Biyoloji', 13, '', 'Genetik Şifre ve Protein Sentezi'),
    ('AYT Biyoloji', 13, '', 'Fotosentez ve Kemosentez'),
    ('AYT Biyoloji', 13, '', 'Hücresel Solunum'),
    ('AYT Biyoloji', 13, '', 'Destek ve Hareket Sistemi'),
    ('AYT Biyoloji', 13, '', 'Sindirim Sistemi'),
    ('AYT Biyoloji', 13, '', 'Dolaşım ve Bağışıklık Sistemi'),
    ('AYT Biyoloji', 13, '', 'Solunum Sistemi'),
    ('AYT Biyoloji', 13, '', 'Üriner Sistem'),
    ('AYT Biyoloji', 13, '', 'Endokrin Sistem'),
    ('AYT Biyoloji', 13, '', 'Sinir Sistemi'),
    ('AYT Biyoloji', 13, '', 'Duyu Organları'),
    ('AYT Biyoloji', 13, '', 'Üreme Sistemi ve Embriyonik Gelişim'),
    ('AYT Biyoloji', 13, '', 'Bitki Biyolojisi'),
    ('AYT Biyoloji', 13, '', 'Komünite ve Popülasyon Ekolojisi'),
    ('AYT Biyoloji', 13, '', 'Canlılar ve Çevre'),
]


class Command(BaseCommand):
    help = 'TYT yayınları, dersleri ve konuları yükler (PDF 2026 konuları)'

    def handle(self, *args, **options):
        self.stdout.write('Yayınlar oluşturuluyor...')
        for name in PUBLISHERS:
            Publisher.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS(f'  {len(PUBLISHERS)} yayın hazır'))

        self.stdout.write('Konular güncelleniyor...')
        subject_cache = {}
        added = updated = 0

        for batch, exam_type in [(TYT_TOPICS, 'TYT'), (AYT_TOPICS, 'AYT')]:
            for subject_name, q_count, sub_cat, topic_name in batch:
                if subject_name not in subject_cache:
                    subj, _ = Subject.objects.get_or_create(
                        exam_type=exam_type, name=subject_name,
                        defaults={'question_count': q_count},
                    )
                    if subj.question_count != q_count:
                        subj.question_count = q_count
                        subj.save(update_fields=['question_count'])
                    subject_cache[subject_name] = subj

                subj = subject_cache[subject_name]
                topic, created = Topic.objects.get_or_create(
                    subject=subj, name=topic_name,
                    defaults={'sub_category': sub_cat},
                )
                if created:
                    added += 1
                elif topic.sub_category != sub_cat:
                    topic.sub_category = sub_cat
                    topic.save(update_fields=['sub_category'])
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'  {added} konu eklendi, {updated} konu güncellendi'
        ))
        self.stdout.write(self.style.SUCCESS('Seed tamamlandı!'))

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

    # ── SOSYAL — TARİH ─────────────────────────────────────────────
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Tarih ve Zaman'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'İnsanlığın İlk Dönemleri'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'İlk ve Orta Çağlarda Türk Dünyası'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'İslam Medeniyetinin Doğuşu ve İlk İslam Devletleri'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', "Türklerin İslamiyet'i Kabulü ve İlk Türk İslam Devletleri"),
    ('TYT Sosyal Bilimler', 20, 'Tarih', "Orta Çağ'da Dünya"),
    ('TYT Sosyal Bilimler', 20, 'Tarih', "Yerleşme ve Devletleşme Sürecinde Selçuklu Türkiye'si"),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Beylikten Devlete Osmanlı Siyaseti'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Devletleşme Sürecinde Savaşçılar ve Askerler'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Beylikten Devlete Osmanlı Medeniyeti'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Dünya Gücü Osmanlı'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Sultan ve Osmanlı Merkez Teşkilatı'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Klasik Çağda Osmanlı Toplum Düzeni'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Değişen Dünya Dengeleri Karşısında Osmanlı Siyaseti'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Değişim Çağında Avrupa ve Osmanlı'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Uluslararası İlişkilerde Denge Stratejisi (1774-1914)'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Devrimler Çağında Değişen Devlet-Toplum İlişkileri'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Sermaye ve Emek'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'XIX. ve XX. Yüzyılda Değişen Gündelik Hayat'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'XX. Yüzyıl Başlarında Osmanlı Devleti ve Dünya'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Milli Mücadele'),
    ('TYT Sosyal Bilimler', 20, 'Tarih', 'Atatürkçülük ve Türk İnkılabı'),

    # ── SOSYAL — COĞRAFYA ──────────────────────────────────────────
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Doğa ve İnsan'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', "Dünya'nın Şekli ve Hareketleri"),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Coğrafi Konum'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Harita Bilgisi'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'İklim Bilgisi'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', "Dünya'nın Tektonik Oluşumu"),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Jeolojik Zamanlar'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'İç Kuvvetler / Dış Kuvvetler'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Kayaçlar'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', "Türkiye'nin Yer Şekilleri"),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Su - Toprak ve Bitkiler'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Nüfus'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', "Türkiye'de Nüfus"),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Göç'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Ekonomik Faaliyetler'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Bölgeler'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Uluslararası Ulaşım Hatları'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Çevre ve Toplum'),
    ('TYT Sosyal Bilimler', 20, 'Coğrafya', 'Doğal Afetler'),

    # ── SOSYAL — FELSEFE ───────────────────────────────────────────
    ('TYT Sosyal Bilimler', 20, 'Felsefe', 'Felsefenin Konusu'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', 'Bilgi Felsefesi'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', 'Varlık Felsefesi'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', 'Ahlak Felsefesi'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', 'Sanat Felsefesi'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', 'Din Felsefesi'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', 'Siyaset Felsefesi'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', 'Bilim Felsefesi'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', 'İlk Çağ Felsefesi'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', '2. ve 15. Yüzyıl Felsefeleri'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', '15. ve 17. Yüzyıl Felsefeleri'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', '18. ve 19. Yüzyıl Felsefeleri'),
    ('TYT Sosyal Bilimler', 20, 'Felsefe', '20. Yüzyıl Felsefesi'),

    # ── SOSYAL — DİN KÜLTÜRÜ ───────────────────────────────────────
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Bilgi ve İnanç'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Din ve İslam'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'İslam ve İbadet'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Gençlik ve Değerler'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'İslam Medeniyeti ve Özellikleri'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Allah İnancı ve İnsan'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', "Allah'ın Varlığı ve Birliği"),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', "Allah'ın İsim ve Sıfatları"),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', "Kur'an-ı Kerim'de İnsan ve Özellikleri"),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'İnsanın Allah İle İrtibatı'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', "Kur'an-ı Kerim'de Gençler"),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Bir Genç Olarak Hz. Muhammed'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Hz. Muhammed ve Gençler'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Bazı Genç Sahabeler'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Din ve Aile'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Din, Kültür ve Sanat'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Din ve Çevre'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Din ve Sosyal Değişim'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Din ve Ekonomi'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Din ve Sosyal Adalet'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'İslam Ahlakı'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Dinî Yorum Farklılıklarının Sebepleri'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'Dinî Yorumlarla İlgili Bazı Kavramlar'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'İslam Düşüncesinde İtikadi ve Siyasi Yorumlar'),
    ('TYT Sosyal Bilimler', 20, 'Din Kültürü', 'İslam Düşüncesinde Fıkhi Yorumlar'),

    # ── FEN — FİZİK ────────────────────────────────────────────────
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Fizik Bilimine Giriş'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Madde ve Özellikleri'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Hareket ve Kuvvet'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'İş, Güç ve Enerji I'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Isı, Sıcaklık ve Genleşme'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Dinamik'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'İş, Güç ve Enerji II'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Elektrostatik'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Elektrik ve Manyetizma'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Basınç'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Kaldırma Kuvveti'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Dalgalar'),
    ('TYT Fen Bilimleri', 20, 'Fizik', 'Optik'),

    # ── FEN — KİMYA ────────────────────────────────────────────────
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Kimya Bilimi'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Atomun Yapısı'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Periyodik Sistem'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Maddenin Halleri'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Kimyasal Türler Arası Etkileşimler'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Kimyasal Hesaplamalar'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Kimyanın Temel Kanunları'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Asit, Baz ve Tuz'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Karışımlar'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Endüstride ve Canlılarda Enerji'),
    ('TYT Fen Bilimleri', 20, 'Kimya', 'Kimya Her Yerde'),

    # ── FEN — BİYOLOJİ ─────────────────────────────────────────────
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Canlıların Ortak Özellikleri'),
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Canlıların Temel Bileşenleri'),
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Hücre ve Organelleri'),
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Hücre Zarından Madde Geçişi'),
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Canlıların Sınıflandırılması'),
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Mitoz ve Eşeysiz Üreme'),
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Mayoz ve Eşeyli Üreme'),
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Kalıtım'),
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Ekosistem Ekolojisi'),
    ('TYT Fen Bilimleri', 20, 'Biyoloji', 'Güncel Çevre Sorunları'),

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

        for subject_name, q_count, sub_cat, topic_name in TYT_TOPICS:
            if subject_name not in subject_cache:
                subj, _ = Subject.objects.get_or_create(exam_type='TYT', name=subject_name)
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

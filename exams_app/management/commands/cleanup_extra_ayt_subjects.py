"""
Idempotent cleanup for AYT scope reduction to SAY-only (4 subjects, 70 topics).

For subjects that should be fully excluded (AYT Geometri, AYT Türk Dili ve Edebiyatı,
AYT Tarih, AYT Coğrafya): sets subject.excluded_from_planning=True and deletes topics
that are not FK-referenced. Referenced topics are marked topic.excluded_from_planning=True
so the engine ignores them in new plan generation.

For legacy AYT Matematik topic names superseded by the new SAY taxonomy: marks those
topics as excluded_from_planning=True (or deletes if unreferenced).

Safe to re-run (idempotent).
"""
from django.core.management.base import BaseCommand
from django.db import transaction


EXCLUDED_SUBJECTS = [
    'AYT Geometri',
    'AYT Türk Dili ve Edebiyatı',
    'AYT Tarih',
    'AYT Coğrafya',
]

# Old AYT Matematik topic names not in the 12-topic SAY list
LEGACY_AYT_MAT_NAMES = [
    'Denklemler ve Eşitsizlikler',
    'Limit ve Süreklilik',
    'Analitik Geometri',
    'Katı Cisimler',
    'Olasılık ve Kombinatorik',
]

# Old AYT Fizik names that are superseded by new canonical names
LEGACY_AYT_FIZ_NAMES = [
    'Bir Boyutlu Hareket',
    'İki Boyutlu Hareket',
    'Tork ve Denge',
    'Gravitasyon',
    'Elektrostatik',
    'Elektrik Akımı',
    'Manyetizma ve Elektromanyetik İndüksiyon',
    'Dalgalar ve Optik',
    'Modern Fizik',
]

# Old AYT Kimya names superseded by new canonical names
LEGACY_AYT_KIM_NAMES = [
    'Atomun Kuantum Modeli',
    'Kimyasal Türler',
    'Maddenin Halleri ve Çözeltiler',
    'Reaksiyon Hızı',
    'Organik Kimyaya Giriş',
    'Karbonhidratlar ve Yağlar',
    'Proteinler ve Nükleik Asitler',
    'Polimer Kimyası',
    'Enerjik Maddeler ve Çevre',
]

# Old AYT Biyoloji names superseded by new canonical names
LEGACY_AYT_BIY_NAMES = [
    'Hücre Biyolojisi',
    'Metabolizma',
    'Fotosentez ve Solunum',
    'DNA ve Gen Kavramı',
    'Genetik Şifre ve Protein Sentezi',  # same name as new — keep this one
    'Mitoz ve Hücre Döngüsü',
    'Mayoz ve Eşeyli Üreme',
    'Kalıtım ve Mendel Genetiği',
    'Sinir Sistemi',                     # same name as new — keep this one
    'Endokrin Sistem',                   # same name as new — keep this one
    'Duyu Organları',                    # same name as new — keep this one
    'İnsanda Üreme ve Gelişme',
    'Popülasyon ve Evrim',
]

# New canonical names to keep — don't mark these as excluded even if in LEGACY list
CANONICAL_AYT_BIY = {
    'Genetik Şifre ve Protein Sentezi',
    'Sinir Sistemi',
    'Endokrin Sistem',
    'Duyu Organları',
}
CANONICAL_AYT_FIZ = set()   # all new Fizik names are unique from old ones


class Command(BaseCommand):
    help = 'Marks non-SAY AYT subjects/topics as excluded_from_planning. FK-safe and idempotent.'

    def handle(self, *args, **opts):
        from exams_app.models import Subject, Topic, ExamResult
        try:
            from exams_app.models import ExamTopicError, BransTopicError, StudentTask
        except ImportError:
            ExamTopicError = BransTopicError = StudentTask = None
        try:
            from curriculum_app.models import MacroPlanTopic, MacroPlanWeekTopic
        except ImportError:
            MacroPlanTopic = MacroPlanWeekTopic = None

        def is_referenced(t):
            checks = []
            if MacroPlanTopic:
                checks.append(MacroPlanTopic.objects.filter(topic=t).exists())
            if MacroPlanWeekTopic:
                checks.append(MacroPlanWeekTopic.objects.filter(topic=t).exists())
            if StudentTask:
                checks.append(StudentTask.objects.filter(topic=t).exists())
            if ExamTopicError:
                checks.append(ExamTopicError.objects.filter(topic=t).exists())
            if BransTopicError:
                checks.append(BransTopicError.objects.filter(topic=t).exists())
            return any(checks)

        def handle_legacy_topics(subject_name, legacy_names, keep_canonical=None):
            keep_canonical = keep_canonical or set()
            subj = Subject.objects.filter(exam_type='AYT', name=subject_name).first()
            if not subj:
                return
            for legacy_name in legacy_names:
                if legacy_name in keep_canonical:
                    continue
                t = Topic.objects.filter(subject=subj, name=legacy_name).first()
                if not t:
                    continue
                if t.excluded_from_planning:
                    continue
                if is_referenced(t):
                    t.excluded_from_planning = True
                    t.save(update_fields=['excluded_from_planning'])
                    self.stdout.write(f'  EXCL {subject_name}/{legacy_name} (referenced — flagged)')
                else:
                    t.delete()
                    self.stdout.write(f'  DEL  {subject_name}/{legacy_name}')

        removed_subjects = marked_excluded_subjects = 0

        with transaction.atomic():
            # Legacy topic cleanup for SAY subjects
            handle_legacy_topics('AYT Matematik', LEGACY_AYT_MAT_NAMES)
            handle_legacy_topics('AYT Fizik', LEGACY_AYT_FIZ_NAMES)
            handle_legacy_topics('AYT Kimya', LEGACY_AYT_KIM_NAMES)
            handle_legacy_topics('AYT Biyoloji', LEGACY_AYT_BIY_NAMES, keep_canonical=CANONICAL_AYT_BIY)

            # Fully excluded subjects
            for subj_name in EXCLUDED_SUBJECTS:
                subj = Subject.objects.filter(exam_type='AYT', name=subj_name).first()
                if not subj:
                    continue
                if not subj.excluded_from_planning:
                    subj.excluded_from_planning = True
                    subj.save(update_fields=['excluded_from_planning'])
                    marked_excluded_subjects += 1
                    self.stdout.write(f'  EXCL subject {subj_name}')
                for t in list(subj.topics.all()):
                    if t.excluded_from_planning:
                        continue
                    if is_referenced(t):
                        t.excluded_from_planning = True
                        t.save(update_fields=['excluded_from_planning'])
                        self.stdout.write(f'  EXCL topic {subj_name}/{t.name}')
                    else:
                        t.delete()
                        self.stdout.write(f'  DEL  topic {subj_name}/{t.name}')
                if not subj.topics.exists():
                    if not ExamResult.objects.filter(subject=subj).exists():
                        subj.delete()
                        removed_subjects += 1
                        self.stdout.write(f'  DEL  subject row {subj_name}')

        # Final count summary
        from exams_app.models import Topic as T
        active_ayt = T.objects.filter(
            subject__exam_type='AYT',
            subject__excluded_from_planning=False,
            excluded_from_planning=False,
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f'Done: {marked_excluded_subjects} subjects flagged, '
            f'{removed_subjects} subjects deleted. '
            f'Active AYT topics for planning: {active_ayt} (target: 70)'
        ))

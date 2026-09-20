"""
AYT alan → allowed subjects mapping and subject-group helpers.
Shared by konu_takip_app and struggle_app so the map never drifts.

Two separate maps intentionally:
  AYT_ALAN_MAP         — Konu Takip: only subjects that have konu_takip_topics loaded.
                         Geometri excluded because KT has no topics for it.
  STRUGGLE_AYT_ALAN_MAP — Struggle questions: same base map + AYT Geometri for SAY/EA.
                          Topic is nullable on struggle questions, so no topics required.
"""

AYT_ALAN_MAP = {
    'SAY': {'AYT Matematik', 'AYT Fizik', 'AYT Kimya', 'AYT Biyoloji'},
    'EA':  {'AYT Matematik', 'AYT Türk Dili ve Edebiyatı'},
    'SOZ': {'AYT Türk Dili ve Edebiyatı', 'AYT Tarih 2', 'AYT Coğrafya 2', 'AYT Felsefe Grubu'},
    'DIL': {'AYT Yabancı Dil'},
}
DEFAULT_AYT = AYT_ALAN_MAP['SAY']  # blank alan → SAY subjects

# Derived map for the struggle-question add-form — adds AYT Geometri to SAY/EA.
# Do NOT use this for Konu Takip subject lists (KT has no Geometri topics).
STRUGGLE_AYT_ALAN_MAP = {
    'SAY': AYT_ALAN_MAP['SAY'] | {'AYT Geometri'},
    'EA':  AYT_ALAN_MAP['EA']  | {'AYT Geometri'},
    'SOZ': AYT_ALAN_MAP['SOZ'],
    'DIL': AYT_ALAN_MAP['DIL'],
}
STRUGGLE_DEFAULT_AYT = STRUGGLE_AYT_ALAN_MAP['SAY']


def subject_groups(student):
    """Return (tyt_subjects, ayt_subjects) for Konu Takip — only subjects with loaded topics."""
    from exams_app.models import Subject
    all_subjects = list(
        Subject.objects.filter(konu_takip_topics__isnull=False)
        .distinct()
        .order_by('name')
    )
    ayt_allowed = AYT_ALAN_MAP.get(student.alan, DEFAULT_AYT)
    tyt = [s for s in all_subjects if s.name.startswith('TYT ')]
    ayt = [s for s in all_subjects if s.name.startswith('AYT ') and s.name in ayt_allowed]
    return tyt, ayt


def struggle_subject_groups(student):
    """
    Return (tyt_subjects, ayt_subjects) for the struggle-question add form.

    Unlike subject_groups(), this queries ALL TYT/AYT subjects regardless of whether
    they have konu_takip_topics (so Geometri appears), and uses STRUGGLE_AYT_ALAN_MAP
    which adds AYT Geometri for SAY/EA.

    Applies the same exclusion filter as the YouTube-playlist import:
      - excluded_from_planning=True  (e.g. "TYT Problemler")
      - explicit umbrella names      (e.g. "TYT Fen Bilimleri", "TYT Sosyal Bilimler")
    """
    from django.db.models import Q
    from exams_app.models import Subject
    all_subjects = list(
        Subject.objects
        .filter(Q(name__startswith='TYT ') | Q(name__startswith='AYT '))
        .exclude(excluded_from_planning=True)
        .exclude(name__in=['TYT Fen Bilimleri', 'TYT Sosyal Bilimler'])
        .order_by('name')
    )
    ayt_allowed = STRUGGLE_AYT_ALAN_MAP.get(
        student.alan if student else None,
        STRUGGLE_DEFAULT_AYT,
    )
    tyt = [s for s in all_subjects if s.name.startswith('TYT ')]
    ayt = [s for s in all_subjects if s.name.startswith('AYT ') and s.name in ayt_allowed]
    return tyt, ayt

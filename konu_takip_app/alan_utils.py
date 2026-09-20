"""
AYT alan → allowed subjects mapping and subject-group helper.
Shared by konu_takip_app and struggle_app so the map never drifts.
"""

AYT_ALAN_MAP = {
    'SAY': {'AYT Matematik', 'AYT Fizik', 'AYT Kimya', 'AYT Biyoloji'},
    'EA':  {'AYT Matematik', 'AYT Türk Dili ve Edebiyatı'},
    'SOZ': {'AYT Türk Dili ve Edebiyatı', 'AYT Tarih 2', 'AYT Coğrafya 2', 'AYT Felsefe Grubu'},
    'DIL': {'AYT Yabancı Dil'},
}
DEFAULT_AYT = AYT_ALAN_MAP['SAY']  # blank alan → SAY subjects


def subject_groups(student):
    """Return (tyt_subjects, ayt_subjects) for this student, AYT filtered by alan."""
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

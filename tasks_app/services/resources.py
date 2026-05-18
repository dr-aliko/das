from django.contrib.auth import get_user_model
from django.db import IntegrityError

from tasks_app.models import KaynakKitap

User = get_user_model()


def list_for_student(coach: User, student_id: int, ders: str, sinav_tipi: str) -> list[str]:
    if not all([student_id, ders, sinav_tipi]):
        return []
    qs = KaynakKitap.objects.filter(
        student__coach=coach,
        student_id=student_id,
        ders=ders,
        sinav_tipi=sinav_tipi,
    ).order_by("kitap_adi")
    return [k.kitap_adi for k in qs]


def add(coach: User, student_id: int, kitap_adi: str, ders: str, sinav_tipi: str) -> bool:
    if not all([student_id, kitap_adi, ders, sinav_tipi]):
        return False
    from users_app.models import User as UserModel
    student = UserModel.objects.filter(role='student', coach=coach, pk=student_id).first()
    if not student:
        return False
    try:
        KaynakKitap.objects.get_or_create(
            student=student,
            kitap_adi=kitap_adi.strip(),
            ders=ders,
            sinav_tipi=sinav_tipi,
        )
        return True
    except IntegrityError:
        return False

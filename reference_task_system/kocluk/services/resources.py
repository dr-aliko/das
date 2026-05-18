from django.contrib.auth import get_user_model
from django.db import IntegrityError

from kocluk.models import KaynakKitap, Ogrenci

User = get_user_model()


def list_for_student(
    koc: User, ogrenci_id: int, ders: str, sinav_tipi: str
) -> list[str]:
    if not all([ogrenci_id, ders, sinav_tipi]):
        return []
    qs = KaynakKitap.objects.filter(
        ogrenci__koc=koc,
        ogrenci_id=ogrenci_id,
        ders=ders,
        sinav_tipi=sinav_tipi,
    ).order_by("kitap_adi")
    return [k.kitap_adi for k in qs]


def add(
    koc: User, ogrenci_id: int, kitap_adi: str, ders: str, sinav_tipi: str
) -> bool:
    if not all([ogrenci_id, kitap_adi, ders, sinav_tipi]):
        return False
    ogrenci = Ogrenci.objects.filter(koc=koc, pk=ogrenci_id).first()
    if not ogrenci:
        return False
    try:
        KaynakKitap.objects.get_or_create(
            ogrenci=ogrenci,
            kitap_adi=kitap_adi.strip(),
            ders=ders,
            sinav_tipi=sinav_tipi,
        )
        return True
    except IntegrityError:
        return False

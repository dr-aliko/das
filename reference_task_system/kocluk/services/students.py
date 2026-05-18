from django.contrib.auth import get_user_model
from django.db import IntegrityError

from kocluk.models import Ogrenci

User = get_user_model()


def list_for_koc(koc: User) -> list[Ogrenci]:
    return list(Ogrenci.objects.filter(koc=koc))


def create(koc: User, ad_soyad: str) -> Ogrenci | None:
    ad_soyad = ad_soyad.strip()
    if not ad_soyad:
        return None
    try:
        return Ogrenci.objects.create(koc=koc, ad_soyad=ad_soyad)
    except IntegrityError:
        return None


def update(koc: User, ogrenci_id: int, yeni_ad: str) -> bool:
    yeni_ad = yeni_ad.strip()
    if not yeni_ad:
        return False
    rows = Ogrenci.objects.filter(koc=koc, pk=ogrenci_id).update(ad_soyad=yeni_ad)
    return bool(rows)


def delete(koc: User, ogrenci_id: int) -> bool:
    deleted, _ = Ogrenci.objects.filter(koc=koc, pk=ogrenci_id).delete()
    return bool(deleted)

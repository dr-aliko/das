from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Prefetch

from kocluk.models import GorevGrubu, GrupDetay, Ogrenci

User = get_user_model()


def week_for_student(
    koc: User, ogrenci_id: int, hafta_basi: date, hafta_sonu: date
) -> list[dict]:
    qs = (
        GorevGrubu.objects.filter(
            ogrenci__koc=koc,
            ogrenci_id=ogrenci_id,
            tarih__range=(hafta_basi, hafta_sonu),
        )
        .order_by("tarih", "sira_no")
        .prefetch_related(Prefetch("detaylar", queryset=GrupDetay.objects.all()))
    )
    return [_serialize(g) for g in qs]


def get_one(koc: User, grup_id: int) -> dict | None:
    grup = (
        GorevGrubu.objects.filter(ogrenci__koc=koc, pk=grup_id)
        .prefetch_related("detaylar")
        .first()
    )
    return _serialize(grup) if grup else None


@transaction.atomic
def create(
    koc: User,
    ogrenci_id: int,
    *,
    tarih: date,
    ders_title: str | None,
    ozel_sure_dk: int | None,
    aktivite_tipi: str | None,
    detaylar: list[dict],
    meta: dict | None = None,
) -> GorevGrubu | None:
    ogrenci = Ogrenci.objects.filter(koc=koc, pk=ogrenci_id).first()
    if not ogrenci:
        return None
    next_sira = (
        GorevGrubu.objects.filter(ogrenci=ogrenci, tarih=tarih).aggregate(
            m=Max("sira_no")
        )["m"]
        or 0
    ) + 1
    grup = GorevGrubu.objects.create(
        ogrenci=ogrenci,
        tarih=tarih,
        ders_title=ders_title,
        ozel_sure_dk=ozel_sure_dk,
        aktivite_tipi=aktivite_tipi,
        sira_no=next_sira,
        meta=meta,
    )
    if detaylar:
        GrupDetay.objects.bulk_create(
            [
                GrupDetay(
                    grup=grup,
                    aciklama=d["aciklama"],
                    sure_bilgisi=d.get("sure_bilgisi"),
                )
                for d in detaylar
            ]
        )
    return grup


@transaction.atomic
def update(
    koc: User,
    grup_id: int,
    *,
    tarih: date,
    ders_title: str | None,
    ozel_sure_dk: int | None,
    aktivite_tipi: str | None,
    detaylar: list[dict],
    meta: dict | None = None,
) -> bool:
    grup = GorevGrubu.objects.filter(ogrenci__koc=koc, pk=grup_id).first()
    if not grup:
        return False
    GorevGrubu.objects.filter(pk=grup_id).update(
        tarih=tarih,
        ders_title=ders_title,
        ozel_sure_dk=ozel_sure_dk,
        aktivite_tipi=aktivite_tipi,
        meta=meta,
    )
    grup.detaylar.all().delete()
    if detaylar:
        GrupDetay.objects.bulk_create(
            [
                GrupDetay(
                    grup=grup,
                    aciklama=d["aciklama"],
                    sure_bilgisi=d.get("sure_bilgisi"),
                )
                for d in detaylar
            ]
        )
    return True


def delete(koc: User, grup_id: int) -> bool:
    deleted, _ = GorevGrubu.objects.filter(ogrenci__koc=koc, pk=grup_id).delete()
    return bool(deleted)


@transaction.atomic
def copy_to_date(koc: User, grup_id: int, hedef_tarih: date) -> GorevGrubu | None:
    src = (
        GorevGrubu.objects.filter(ogrenci__koc=koc, pk=grup_id)
        .prefetch_related("detaylar")
        .first()
    )
    if not src:
        return None
    next_sira = (
        GorevGrubu.objects.filter(ogrenci=src.ogrenci, tarih=hedef_tarih).aggregate(
            m=Max("sira_no")
        )["m"]
        or 0
    ) + 1
    yeni = GorevGrubu.objects.create(
        ogrenci=src.ogrenci,
        tarih=hedef_tarih,
        ders_title=src.ders_title,
        ozel_sure_dk=src.ozel_sure_dk,
        aktivite_tipi=src.aktivite_tipi,
        sira_no=next_sira,
        meta=src.meta,
    )
    GrupDetay.objects.bulk_create(
        [
            GrupDetay(grup=yeni, aciklama=d.aciklama, sure_bilgisi=d.sure_bilgisi)
            for d in src.detaylar.all()
        ]
    )
    return yeni


@transaction.atomic
def swap_order(koc: User, suruklenen_id: int, birakilan_id: int) -> bool:
    a = (
        GorevGrubu.objects.select_for_update()
        .filter(ogrenci__koc=koc, pk=suruklenen_id)
        .first()
    )
    b = (
        GorevGrubu.objects.select_for_update()
        .filter(ogrenci__koc=koc, pk=birakilan_id)
        .first()
    )
    if not (a and b and a.ogrenci_id == b.ogrenci_id and a.tarih == b.tarih):
        return False
    a.sira_no, b.sira_no = b.sira_no, a.sira_no
    a.save(update_fields=["sira_no"])
    b.save(update_fields=["sira_no"])
    return True


def _serialize(grup: GorevGrubu) -> dict:
    return {
        "id": grup.id,
        "tarih": grup.tarih.isoformat() if grup.tarih else None,
        "ders_title": grup.ders_title,
        "aktivite_tipi": grup.aktivite_tipi,
        "ozel_sure_dk": grup.ozel_sure_dk,
        "sira_no": grup.sira_no,
        "meta": grup.meta,
        "detaylar": [
            {
                "id": d.id,
                "aciklama": d.aciklama,
                "sure_bilgisi": d.sure_bilgisi,
            }
            for d in grup.detaylar.all()
        ],
    }

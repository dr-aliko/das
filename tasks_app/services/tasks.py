from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Prefetch

from tasks_app.models import GorevGrubu, GrupDetay

User = get_user_model()


# ── Read ──────────────────────────────────────────────────────────────────────

def week_for_student(
    coach: User, student_id: int, hafta_basi: date, hafta_sonu: date
) -> list[dict]:
    qs = (
        GorevGrubu.objects.filter(
            student__coach=coach,
            student_id=student_id,
            tarih__range=(hafta_basi, hafta_sonu),
        )
        .order_by("tarih", "sira_no")
        .prefetch_related(Prefetch("detaylar", queryset=GrupDetay.objects.all()))
    )
    return [_serialize(g) for g in qs]


def get_one(coach: User, grup_id: int) -> dict | None:
    grup = (
        GorevGrubu.objects.filter(student__coach=coach, pk=grup_id)
        .prefetch_related("detaylar")
        .first()
    )
    return _serialize(grup) if grup else None


def _serialize(grup: GorevGrubu) -> dict:
    return {
        "id": grup.id,
        "tarih": grup.tarih.isoformat() if grup.tarih else None,
        "ders_title": grup.ders_title,
        "aktivite_tipi": grup.aktivite_tipi,
        "ozel_sure_dk": grup.ozel_sure_dk,
        "sira_no": grup.sira_no,
        "meta": grup.meta,
        "is_completed": grup.is_completed,
        "completed_at": grup.completed_at.isoformat() if grup.completed_at else None,
        "tekrar_quality": grup.tekrar_quality,
        "student_can_edit": grup.student_can_edit,
        "detaylar": [
            {
                "id": d.id,
                "aciklama": d.aciklama,
                "sure_bilgisi": d.sure_bilgisi,
            }
            for d in grup.detaylar.all()
        ],
    }


# ── Student versioned view (merged master + copies) ───────────────────────────

def _serialize_with_version(grup: GorevGrubu) -> dict:
    d = _serialize(grup)
    d["is_master"] = grup.is_master
    d["parent_id"] = grup.parent_id
    return d


@transaction.atomic
def _ensure_student_copies(student: User, hafta_basi: date, hafta_sonu: date) -> None:
    """Eagerly fork all student_can_edit=True master tasks that have no copy yet."""
    masters = list(
        GorevGrubu.objects.filter(
            student=student, is_master=True, student_can_edit=True,
            is_hidden_by_student=False,          # skip tasks student has hidden
            tarih__range=(hafta_basi, hafta_sonu),
        ).prefetch_related("detaylar")
    )
    if not masters:
        return
    master_ids = [m.id for m in masters]
    existing_parent_ids = set(
        GorevGrubu.objects.filter(
            student=student, is_master=False, parent_id__in=master_ids,
        ).values_list("parent_id", flat=True)
    )
    for master in masters:
        if master.id in existing_parent_ids:
            continue
        copy = GorevGrubu.objects.create(
            student=student, tarih=master.tarih,
            aktivite_tipi=master.aktivite_tipi,
            ozel_sure_dk=master.ozel_sure_dk,
            ders_title=master.ders_title,
            sira_no=master.sira_no,
            meta=master.meta,
            is_master=False, parent=master,
            student_can_edit=True,
        )
        GrupDetay.objects.bulk_create([
            GrupDetay(grup=copy, aciklama=d.aciklama, sure_bilgisi=d.sure_bilgisi)
            for d in master.detaylar.all()
        ])


def week_for_own_student(student: User, hafta_basi: date, hafta_sonu: date) -> list[dict]:
    """Merged view: student copies override masters; read-only masters shown where no copy exists."""
    _ensure_student_copies(student, hafta_basi, hafta_sonu)
    all_tasks = list(
        GorevGrubu.objects.filter(student=student, tarih__range=(hafta_basi, hafta_sonu))
        .order_by("tarih", "sira_no")
        .prefetch_related(Prefetch("detaylar", queryset=GrupDetay.objects.all()))
    )
    copy_parent_ids = {t.parent_id for t in all_tasks if not t.is_master and t.parent_id}
    visible = [
        t for t in all_tasks
        if not t.is_master                                        # always show copies
        or (t.id not in copy_parent_ids and not t.is_hidden_by_student)  # show masters only if no copy AND not hidden
    ]
    return [_serialize_with_version(g) for g in visible]


def toggle_complete(student: User, grup_id: int, quality: str | None = None) -> dict | None:
    from django.utils import timezone
    grup = GorevGrubu.objects.filter(student=student, pk=grup_id).first()
    if not grup:
        return None
    if grup.is_completed and quality is None:
        # Undo completion
        grup.is_completed = False
        grup.completed_at = None
        grup.tekrar_quality = None
    else:
        grup.is_completed = True
        grup.completed_at = timezone.now()
        if quality in ("easy", "medium", "hard"):
            grup.tekrar_quality = quality
    grup.save(update_fields=["is_completed", "completed_at", "tekrar_quality"])
    return _serialize(grup)


# ── Write ─────────────────────────────────────────────────────────────────────

@transaction.atomic
def create(
    coach: User,
    student_id: int,
    *,
    tarih: date,
    ders_title: str | None,
    ozel_sure_dk: int | None,
    aktivite_tipi: str | None,
    detaylar: list[dict],
    meta: dict | None = None,
) -> GorevGrubu | None:
    from users_app.models import User as UserModel
    student = UserModel.objects.filter(role='student', coach=coach, pk=student_id).first()
    if not student:
        return None
    next_sira = (
        GorevGrubu.objects.filter(student=student, tarih=tarih)
        .aggregate(m=Max("sira_no"))["m"] or 0
    ) + 1
    grup = GorevGrubu.objects.create(
        student=student,
        tarih=tarih,
        ders_title=ders_title,
        ozel_sure_dk=ozel_sure_dk,
        aktivite_tipi=aktivite_tipi,
        sira_no=next_sira,
        meta=meta,
    )
    if detaylar:
        GrupDetay.objects.bulk_create([
            GrupDetay(grup=grup, aciklama=d["aciklama"], sure_bilgisi=d.get("sure_bilgisi"))
            for d in detaylar
        ])
    return grup


@transaction.atomic
def update(
    coach: User,
    grup_id: int,
    *,
    tarih: date,
    ders_title: str | None,
    ozel_sure_dk: int | None,
    aktivite_tipi: str | None,
    detaylar: list[dict],
    meta: dict | None = None,
) -> bool:
    grup = GorevGrubu.objects.filter(student__coach=coach, pk=grup_id).first()
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
        GrupDetay.objects.bulk_create([
            GrupDetay(grup=grup, aciklama=d["aciklama"], sure_bilgisi=d.get("sure_bilgisi"))
            for d in detaylar
        ])
    return True


def delete(coach: User, grup_id: int) -> bool:
    deleted, _ = GorevGrubu.objects.filter(student__coach=coach, pk=grup_id).delete()
    return bool(deleted)


@transaction.atomic
def copy_to_date(coach: User, grup_id: int, hedef_tarih: date) -> GorevGrubu | None:
    src = (
        GorevGrubu.objects.filter(student__coach=coach, pk=grup_id)
        .prefetch_related("detaylar")
        .first()
    )
    if not src:
        return None
    next_sira = (
        GorevGrubu.objects.filter(student=src.student, tarih=hedef_tarih)
        .aggregate(m=Max("sira_no"))["m"] or 0
    ) + 1
    yeni = GorevGrubu.objects.create(
        student=src.student,
        tarih=hedef_tarih,
        ders_title=src.ders_title,
        ozel_sure_dk=src.ozel_sure_dk,
        aktivite_tipi=src.aktivite_tipi,
        sira_no=next_sira,
        meta=src.meta,  # preserves meta.videos and all meta fields intact
    )
    GrupDetay.objects.bulk_create([
        GrupDetay(grup=yeni, aciklama=d.aciklama, sure_bilgisi=d.sure_bilgisi)
        for d in src.detaylar.all()
    ])
    return yeni


@transaction.atomic
def swap_order(coach: User, suruklenen_id: int, birakilan_id: int) -> bool:
    a = (
        GorevGrubu.objects.select_for_update()
        .filter(student__coach=coach, pk=suruklenen_id)
        .first()
    )
    b = (
        GorevGrubu.objects.select_for_update()
        .filter(student__coach=coach, pk=birakilan_id)
        .first()
    )
    # Both must exist, belong to the same student, and be on the same date.
    if not (a and b and a.student_id == b.student_id and a.tarih == b.tarih):
        return False
    a.sira_no, b.sira_no = b.sira_no, a.sira_no
    a.save(update_fields=["sira_no"])  # meta is never touched
    b.save(update_fields=["sira_no"])
    return True


# ── Coach permission toggle ───────────────────────────────────────────────────

def toggle_student_can_edit(coach: User, grup_id: int) -> dict | None:
    grup = GorevGrubu.objects.filter(student__coach=coach, pk=grup_id).first()
    if not grup:
        return None
    grup.student_can_edit = not grup.student_can_edit
    grup.save(update_fields=["student_can_edit"])
    return _serialize(grup)


# ── Student-permission-gated mutations ───────────────────────────────────────

@transaction.atomic
def student_update(
    student: User,
    grup_id: int,
    *,
    ozel_sure_dk: int | None,
    aciklama: str | None,
) -> dict | None:
    grup = (
        GorevGrubu.objects.filter(student=student, pk=grup_id, student_can_edit=True)
        .prefetch_related("detaylar")
        .first()
    )
    if not grup:
        return None
    if ozel_sure_dk is not None:
        grup.ozel_sure_dk = ozel_sure_dk
        grup.save(update_fields=["ozel_sure_dk"])
    if aciklama is not None:
        d = grup.detaylar.first()
        if d:
            d.aciklama = aciklama
            d.save(update_fields=["aciklama"])
    return _serialize(grup)


@transaction.atomic
def student_swap_order(student: User, suruklenen_id: int, birakilan_id: int) -> bool:
    a = (
        GorevGrubu.objects.select_for_update()
        .filter(student=student, pk=suruklenen_id, student_can_edit=True)
        .first()
    )
    b = (
        GorevGrubu.objects.select_for_update()
        .filter(student=student, pk=birakilan_id, student_can_edit=True)
        .first()
    )
    if not (a and b and a.tarih == b.tarih):
        return False
    a.sira_no, b.sira_no = b.sira_no, a.sira_no
    a.save(update_fields=["sira_no"])
    b.save(update_fields=["sira_no"])
    return True


# ── Bulk permission (coach) ───────────────────────────────────────────────────

def bulk_set_student_can_edit(
    coach: User, student_id: int, hafta_basi: date, hafta_sonu: date, enabled: bool
) -> int:
    return GorevGrubu.objects.filter(
        student__coach=coach,
        student_id=student_id,
        tarih__range=(hafta_basi, hafta_sonu),
    ).update(student_can_edit=enabled)


# ── Student drag (cross-day copy) ─────────────────────────────────────────────

@transaction.atomic
def student_copy_to_date(student: User, grup_id: int, hedef_tarih: date) -> GorevGrubu | None:
    src = (
        GorevGrubu.objects.filter(student=student, pk=grup_id, student_can_edit=True)
        .prefetch_related("detaylar")
        .first()
    )
    if not src:
        return None
    next_sira = (
        GorevGrubu.objects.filter(student=src.student, tarih=hedef_tarih)
        .aggregate(m=Max("sira_no"))["m"] or 0
    ) + 1
    yeni = GorevGrubu.objects.create(
        student=src.student,
        tarih=hedef_tarih,
        ders_title=src.ders_title,
        ozel_sure_dk=src.ozel_sure_dk,
        aktivite_tipi=src.aktivite_tipi,
        sira_no=next_sira,
        meta=src.meta,
        student_can_edit=src.student_can_edit,
        is_master=False, parent=None,
    )
    GrupDetay.objects.bulk_create([
        GrupDetay(grup=yeni, aciklama=d.aciklama, sure_bilgisi=d.sure_bilgisi)
        for d in src.detaylar.all()
    ])
    return yeni


# ── Student full CRUD (only on non-master rows) ───────────────────────────────

@transaction.atomic
def student_create(
    student: User,
    *,
    tarih: date,
    ders_title: str | None,
    ozel_sure_dk: int | None,
    aktivite_tipi: str | None,
    detaylar: list[dict],
    meta: dict | None = None,
) -> GorevGrubu:
    next_sira = (
        GorevGrubu.objects.filter(student=student, tarih=tarih)
        .aggregate(m=Max("sira_no"))["m"] or 0
    ) + 1
    grup = GorevGrubu.objects.create(
        student=student, tarih=tarih,
        ders_title=ders_title, ozel_sure_dk=ozel_sure_dk,
        aktivite_tipi=aktivite_tipi, sira_no=next_sira,
        meta=meta, is_master=False, parent=None, student_can_edit=True,
    )
    if detaylar:
        GrupDetay.objects.bulk_create([
            GrupDetay(grup=grup, aciklama=d["aciklama"], sure_bilgisi=d.get("sure_bilgisi"))
            for d in detaylar
        ])
    return grup


@transaction.atomic
def student_hide_or_delete(student: User, grup_id: int) -> bool:
    """
    Safe removal for students:
    - Copy of a master  → hide the master (is_hidden_by_student=True) + delete the copy
    - Master visible directly → hide it (is_hidden_by_student=True); never delete
    - Student-added task (no parent) → actually delete (it has no master to preserve)
    """
    grup = GorevGrubu.objects.filter(student=student, pk=grup_id).first()
    if not grup:
        return False
    if grup.is_master:
        # Master task seen directly (no copy exists) — hide it, never delete
        grup.is_hidden_by_student = True
        grup.save(update_fields=["is_hidden_by_student"])
    elif grup.parent_id:
        # Copy of a master — hide the master, delete the copy
        GorevGrubu.objects.filter(pk=grup.parent_id, student=student).update(is_hidden_by_student=True)
        grup.delete()
    else:
        # Student-added task (no master equivalent) — delete outright
        grup.delete()
    return True


# ── Reset (restore master plan) ───────────────────────────────────────────────

def reset_student_week(student: User, hafta_basi: date, hafta_sonu: date) -> int:
    """Student resets their own week — deletes copies AND unhides all hidden masters."""
    deleted, _ = GorevGrubu.objects.filter(
        student=student, is_master=False,
        tarih__range=(hafta_basi, hafta_sonu),
    ).delete()
    # Restore hidden master tasks
    GorevGrubu.objects.filter(
        student=student, is_master=True, is_hidden_by_student=True,
        tarih__range=(hafta_basi, hafta_sonu),
    ).update(is_hidden_by_student=False)
    return deleted


def reset_student_week_by_coach(
    coach: User, student_id: int, hafta_basi: date, hafta_sonu: date
) -> int:
    """Coach resets a student's week — deletes copies AND unhides hidden masters."""
    deleted, _ = GorevGrubu.objects.filter(
        student__coach=coach, student_id=student_id,
        is_master=False, tarih__range=(hafta_basi, hafta_sonu),
    ).delete()
    GorevGrubu.objects.filter(
        student__coach=coach, student_id=student_id,
        is_master=True, is_hidden_by_student=True,
        tarih__range=(hafta_basi, hafta_sonu),
    ).update(is_hidden_by_student=False)
    return deleted

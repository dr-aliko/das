import json
from datetime import date
from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from kocluk.forms import GorevForm, OgrenciForm
from kocluk.services import api_client, tasks, week as week_svc
from kocluk.services import resources, students
from kocluk.services.export import weekly_html, weekly_xlsx
from kocluk.models import Ogrenci


# ── Utility ──────────────────────────────────────────────────────────────────

def _body(request) -> dict:
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


def _safe_json(fn):
    # Temporary: catch unexpected exceptions and return JSON 500 instead of crashing.
    @wraps(fn)
    def wrapper(self, request, *args, **kwargs):
        try:
            return fn(self, request, *args, **kwargs)
        except Exception as e:  # noqa: BLE001
            return JsonResponse({"errors": "Sunucu hatası", "detail": str(e)}, status=500)
    return wrapper


# ── Main page ─────────────────────────────────────────────────────────────────

class HaftaView(LoginRequiredMixin, View):
    def get(self, request):
        ogrenciler = students.list_for_koc(request.user)
        return render(request, "kocluk/hafta.html", {"ogrenciler": ogrenciler})


# ── Ogrenciler ────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class OgrenciListView(LoginRequiredMixin, View):
    @_safe_json
    def get(self, request):
        data = [
            {"id": o.id, "ad_soyad": o.ad_soyad}
            for o in students.list_for_koc(request.user)
        ]
        return JsonResponse({"ogrenciler": data})

    @_safe_json
    def post(self, request):
        form = OgrenciForm(_body(request))
        if not form.is_valid():
            return JsonResponse({"errors": form.errors}, status=400)
        ogr = students.create(request.user, form.cleaned_data["ad_soyad"])
        if not ogr:
            return JsonResponse(
                {"errors": {"ad_soyad": ["Boş veya yinelenen isim"]}}, status=400
            )
        return JsonResponse({"id": ogr.id, "ad_soyad": ogr.ad_soyad}, status=201)


@method_decorator(csrf_exempt, name='dispatch')
class OgrenciDetailView(LoginRequiredMixin, View):
    @_safe_json
    def get(self, request, pk: int):
        ogr = students.list_for_koc(request.user).filter(pk=pk).first()
        if not ogr:
            return JsonResponse({"errors": "Bulunamadı"}, status=404)
        return JsonResponse({"id": ogr.id, "ad_soyad": ogr.ad_soyad})

    @_safe_json
    def put(self, request, pk: int):
        body = _body(request)
        ok = students.update(request.user, pk, body.get("ad_soyad", ""))
        return JsonResponse({"ok": ok}, status=200 if ok else 404)

    @_safe_json
    def delete(self, request, pk: int):
        ok = students.delete(request.user, pk)
        return JsonResponse({"ok": ok}, status=200 if ok else 404)


# ── Görevler ──────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class GorevListView(LoginRequiredMixin, View):
    @_safe_json
    def get(self, request):
        try:
            ogrenci_id = int(request.GET["ogrenci_id"])
            hafta = date.fromisoformat(request.GET["hafta"])
        except (KeyError, ValueError):
            return JsonResponse(
                {"errors": "ogrenci_id ve hafta=YYYY-MM-DD gerekli"}, status=400
            )
        basi, sonu = week_svc.week_bounds(hafta)
        gorevler = tasks.week_for_student(request.user, ogrenci_id, basi, sonu)
        return JsonResponse(
            {
                "hafta_basi": basi.isoformat(),
                "hafta_sonu": sonu.isoformat(),
                "gorevler": gorevler,
                "gunluk_toplamlar": week_svc.daily_totals(gorevler),
            }
        )

    @_safe_json
    def post(self, request):
        body = _body(request)
        form = GorevForm(body)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors}, status=400)
        cd = form.cleaned_data
        ogrenci_id = cd.get("ogrenci_id") or body.get("ogrenci_id")
        if not ogrenci_id:
            return JsonResponse({"errors": "ogrenci_id gerekli"}, status=400)
        meta = None
        if cd["aktivite_tipi"] == "konu_anlatimi":
            meta = {
                "sinav_tipi": body.get("sinav_tipi"),
                "ders_id": body.get("konu_ders_id"),
                "liste_id": body.get("liste_id"),
            }
        grup = tasks.create(
            request.user,
            ogrenci_id,
            tarih=cd["tarih"],
            ders_title=cd["ders_title"],
            ozel_sure_dk=cd.get("ozel_sure_dk"),
            aktivite_tipi=cd["aktivite_tipi"],
            detaylar=cd["detaylar"],
            meta=meta,
        )
        if not grup:
            return JsonResponse({"errors": "Öğrenci bulunamadı"}, status=404)
        return JsonResponse({"id": grup.id}, status=201)


@method_decorator(csrf_exempt, name='dispatch')
class GorevDetailView(LoginRequiredMixin, View):
    @_safe_json
    def get(self, request, pk: int):
        data = tasks.get_one(request.user, pk)
        if not data:
            return JsonResponse({"errors": "Bulunamadı"}, status=404)
        return JsonResponse(data)

    @_safe_json
    def put(self, request, pk: int):
        body = _body(request)
        form = GorevForm(body)
        if not form.is_valid():
            return JsonResponse({"errors": form.errors}, status=400)
        cd = form.cleaned_data
        meta = None
        if cd["aktivite_tipi"] == "konu_anlatimi":
            meta = {
                "sinav_tipi": body.get("sinav_tipi"),
                "ders_id": body.get("konu_ders_id"),
                "liste_id": body.get("liste_id"),
            }
        ok = tasks.update(
            request.user,
            pk,
            tarih=cd["tarih"],
            ders_title=cd["ders_title"],
            ozel_sure_dk=cd.get("ozel_sure_dk"),
            aktivite_tipi=cd["aktivite_tipi"],
            detaylar=cd["detaylar"],
            meta=meta,
        )
        return JsonResponse({"ok": ok}, status=200 if ok else 404)

    @_safe_json
    def delete(self, request, pk: int):
        ok = tasks.delete(request.user, pk)
        return JsonResponse({"ok": ok}, status=200 if ok else 404)


@method_decorator(csrf_exempt, name='dispatch')
class GorevCopyView(LoginRequiredMixin, View):
    @_safe_json
    def post(self, request, pk: int):
        try:
            hedef = date.fromisoformat(_body(request)["hedef_tarih"])
        except (KeyError, ValueError):
            return JsonResponse({"errors": "hedef_tarih gerekli"}, status=400)
        yeni = tasks.copy_to_date(request.user, pk, hedef)
        if not yeni:
            return JsonResponse({"ok": False}, status=404)
        return JsonResponse({"id": yeni.id}, status=201)


@method_decorator(csrf_exempt, name='dispatch')
class GorevReorderView(LoginRequiredMixin, View):
    @_safe_json
    def post(self, request, pk: int):
        try:
            hedef_id = int(_body(request)["hedef_id"])
        except (KeyError, ValueError):
            return JsonResponse({"errors": "hedef_id gerekli"}, status=400)
        ok = tasks.swap_order(request.user, pk, hedef_id)
        return JsonResponse({"ok": ok}, status=200 if ok else 400)


# ── Kaynak kitaplar ───────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class KaynakKitapListView(LoginRequiredMixin, View):
    @_safe_json
    def get(self, request):
        try:
            ogrenci_id = int(request.GET["ogrenci_id"])
        except (KeyError, ValueError):
            return JsonResponse({"errors": "ogrenci_id gerekli"}, status=400)
        ders = request.GET.get("ders", "")
        sinav_tipi = request.GET.get("sinav_tipi", "")
        kitaplar = resources.list_for_student(
            request.user, ogrenci_id, ders, sinav_tipi
        )
        return JsonResponse({"kitaplar": kitaplar})

    @_safe_json
    def post(self, request):
        body = _body(request)
        ok = resources.add(
            request.user,
            body.get("ogrenci_id"),
            body.get("kitap_adi", ""),
            body.get("ders", ""),
            body.get("sinav_tipi", ""),
        )
        return JsonResponse({"ok": ok}, status=201 if ok else 400)


# ── External API proxies ──────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name='dispatch')
class DerslerView(LoginRequiredMixin, View):
    @_safe_json
    def get(self, request):
        return JsonResponse({"dersler": api_client.get_dersler()})


# ── Temporary debug view — remove after fixing /api/dersler ──────────────────

@method_decorator(csrf_exempt, name='dispatch')
class DerslerDebugView(LoginRequiredMixin, View):
    def get(self, request):
        import requests as req
        from django.conf import settings
        base = getattr(settings, "EXTERNAL_API_BASE_URL", "")
        url = f"{base}/dersler"
        try:
            r = req.get(url, timeout=10)
            return JsonResponse({
                "url": url,
                "status": r.status_code,
                "raw": r.text[:2000],
                "parsed": r.json(),
            }, safe=False)
        except Exception as e:
            return JsonResponse({"url": url, "error": str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class OynatmaListeleriView(LoginRequiredMixin, View):
    @_safe_json
    def get(self, request, ders_id: int):
        tip = request.GET.get("tip", "")
        return JsonResponse(
            {"listeler": api_client.get_oynatma_listeleri(ders_id, tip)}
        )


@method_decorator(csrf_exempt, name='dispatch')
class VideolarView(LoginRequiredMixin, View):
    @_safe_json
    def get(self, request, liste_id: int):
        return JsonResponse({"videolar": api_client.get_videolar(liste_id)})


# ── Exports ───────────────────────────────────────────────────────────────────

class ExportHtmlView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            ogrenci_id = int(request.GET["ogrenci_id"])
            hafta = date.fromisoformat(request.GET["hafta"])
        except (KeyError, ValueError):
            return HttpResponseBadRequest("ogrenci_id ve hafta=YYYY-MM-DD gerekli")
        html = weekly_html(request.user, ogrenci_id, hafta)
        return HttpResponse(
            html,
            content_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="hafta_{hafta}.html"'},
        )


class ExportXlsxView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            ogrenci_id = int(request.GET["ogrenci_id"])
            hafta = date.fromisoformat(request.GET["hafta"])
        except (KeyError, ValueError):
            return HttpResponseBadRequest("ogrenci_id ve hafta=YYYY-MM-DD gerekli")
        xlsx_bytes = weekly_xlsx(request.user, ogrenci_id, hafta)
        return HttpResponse(
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="hafta_{hafta}.xlsx"'},
        )

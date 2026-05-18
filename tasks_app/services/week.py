from datetime import date, timedelta


def week_bounds(reference: date) -> tuple[date, date]:
    monday = reference - timedelta(days=reference.weekday())
    return monday, monday + timedelta(days=6)


def daily_totals(gorevler: list[dict]) -> dict[int, int]:
    """{weekday_index: total_minutes} for 0=Monday … 6=Sunday."""
    totals: dict[int, int] = {i: 0 for i in range(7)}
    for g in gorevler:
        if g.get("ozel_sure_dk"):
            tarih = g["tarih"]
            if isinstance(tarih, str):
                tarih = date.fromisoformat(tarih)
            totals[tarih.weekday()] += g["ozel_sure_dk"]
    return totals


def format_minutes(toplam_dk: int) -> str:
    if toplam_dk <= 0:
        return "Toplam: 0 dk"
    saat, dk = divmod(toplam_dk, 60)
    return f"Toplam: {saat}s {dk}dk"

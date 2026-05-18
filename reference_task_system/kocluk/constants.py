from kocluk.models import AktiviteTipi

RENK_MAP: dict[str, str] = {
    AktiviteTipi.KONU_ANLATIMI: "#e9f5ff",
    AktiviteTipi.SORU_COZUMU: "#fff4e6",
    AktiviteTipi.TEKRAR: "#e6ffed",
}

BORDER_MAP: dict[str, str] = {
    AktiviteTipi.KONU_ANLATIMI: "#b3d7ff",
    AktiviteTipi.SORU_COZUMU: "#ffdcb3",
    AktiviteTipi.TEKRAR: "#b3ffc6",
}

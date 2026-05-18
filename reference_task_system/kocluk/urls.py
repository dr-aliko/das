from django.urls import path

from kocluk import views

urlpatterns = [
    # Main page
    path("", views.HaftaView.as_view(), name="hafta"),

    # Students
    path("api/ogrenciler", views.OgrenciListView.as_view(), name="api-ogrenciler"),
    path("api/ogrenciler/<int:pk>", views.OgrenciDetailView.as_view(), name="api-ogrenci-detail"),

    # Tasks
    path("api/gorevler", views.GorevListView.as_view(), name="api-gorevler"),
    path("api/gorev/<int:pk>", views.GorevDetailView.as_view(), name="api-gorev-detail"),
    path("api/gorev/<int:pk>/copy", views.GorevCopyView.as_view(), name="api-gorev-copy"),
    path("api/gorev/<int:pk>/reorder", views.GorevReorderView.as_view(), name="api-gorev-reorder"),

    # Resource books
    path("api/kaynak-kitaplar", views.KaynakKitapListView.as_view(), name="api-kaynak-kitaplar"),

    # External API proxies
    path("api/dersler", views.DerslerView.as_view(), name="api-dersler"),
    path("api/oynatma-listeleri/<int:ders_id>", views.OynatmaListeleriView.as_view(), name="api-oynatma-listeleri"),
    path("api/videolar/<int:liste_id>", views.VideolarView.as_view(), name="api-videolar"),

    # Temporary debug
    path("api/debug/dersler", views.DerslerDebugView.as_view(), name="debug-dersler"),

    # Exports
    path("export/hafta.html", views.ExportHtmlView.as_view(), name="export-html"),
    path("export/hafta.xlsx", views.ExportXlsxView.as_view(), name="export-xlsx"),
]

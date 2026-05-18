from django.urls import path

from tasks_app import views

app_name = 'tasks'

urlpatterns = [
    path('', views.HaftaView.as_view(), name='hafta'),

    # Students
    path('api/students', views.StudentListView.as_view(), name='api-students'),

    # Tasks
    path('api/gorevler', views.GorevListView.as_view(), name='api-gorevler'),
    path('api/gorev/<int:pk>', views.GorevDetailView.as_view(), name='api-gorev-detail'),
    path('api/gorev/<int:pk>/copy', views.GorevCopyView.as_view(), name='api-gorev-copy'),
    path('api/gorev/<int:pk>/reorder', views.GorevReorderView.as_view(), name='api-gorev-reorder'),
    path('api/gorev/<int:pk>/permit', views.GorevStudentPermitView.as_view(), name='api-gorev-permit'),
    path('api/bulk-edit-permission/', views.GorevBulkPermitView.as_view(), name='api-bulk-permit'),
    path('api/reset-student-week/', views.CoachStudentResetView.as_view(), name='api-reset-student'),

    # Kaynak kitaplar
    path('api/kaynak-kitaplar', views.KaynakKitapListView.as_view(), name='api-kaynak-kitaplar'),

    # Export
    path('export/hafta.xlsx', views.ExportXlsxView.as_view(), name='export-xlsx'),

    # External API proxies
    path('api/dersler', views.DerslerView.as_view(), name='api-dersler'),
    path('api/oynatma-listeleri/<int:ders_id>', views.OynatmaListeleriView.as_view(), name='api-oynatma-listeleri'),
    path('api/videolar/<int:liste_id>', views.VideolarView.as_view(), name='api-videolar'),
]

from django.urls import path

from tasks_app import views

app_name = 'student_tasks'

urlpatterns = [
    path('', views.StudentHaftaView.as_view(), name='hafta'),
    path('api/gorevler', views.StudentGorevListView.as_view(), name='api-gorevler'),
    path('api/gorev/new', views.StudentGorevCreateView.as_view(), name='api-gorev-new'),
    path('api/complete/<int:pk>', views.StudentGorevCompleteView.as_view(), name='api-complete'),
    path('api/gorev/<int:pk>/edit', views.StudentGorevEditView.as_view(), name='api-gorev-edit'),
    path('api/gorev/<int:pk>/delete', views.StudentGorevDeleteView.as_view(), name='api-gorev-delete'),
    path('api/gorev/<int:pk>/reorder', views.StudentGorevReorderView.as_view(), name='api-gorev-reorder'),
    path('api/gorev/<int:pk>/copy', views.StudentGorevCopyView.as_view(), name='api-gorev-copy'),
    path('api/reset/', views.StudentResetView.as_view(), name='api-reset'),
    path('export/hafta.xlsx', views.StudentExportXlsxView.as_view(), name='export-xlsx'),
]

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView
from exams_app.views import brans_export_html, brans_export_xlsx, brans_hub_student, brans_subject_detail_student
from users_app.views import home_redirect, yakinda_analiz, yakinda_profil, profil_view, theme_save, activity_calendar_api

urlpatterns = [
    path('manifest.webmanifest',
         TemplateView.as_view(template_name='pwa/manifest.webmanifest',
                              content_type='application/manifest+json'),
         name='manifest'),
    path('service-worker.js',
         TemplateView.as_view(template_name='pwa/service-worker.js',
                              content_type='application/javascript'),
         name='service_worker'),
    path('offline/',
         TemplateView.as_view(template_name='pwa/offline.html'),
         name='offline'),

    path('admin/', admin.site.urls),
    path('', home_redirect, name='home'),
    path('auth/', include('users_app.urls', namespace='users_app')),
    path('student/', include('exams_app.student_urls', namespace='student')),
    path('coach/', include('exams_app.coach_urls', namespace='coach')),
    path('coach/tasks/', include('tasks_app.urls', namespace='tasks')),
    path('student/tasks/', include('tasks_app.student_urls', namespace='student_tasks')),
    path('brans/', brans_hub_student, name='brans_hub'),
    path('brans/export.xlsx', brans_export_xlsx, name='brans_export_xlsx'),
    path('brans/export.html', brans_export_html, name='brans_export_html'),
    path('brans/<slug:subject_slug>/', brans_subject_detail_student, name='brans_subject_detail'),
    path('analiz/', RedirectView.as_view(pattern_name='brans_hub', permanent=True), name='yakinda_analiz'),
    path('profil/', profil_view,    name='profil'),
    path('profil/theme/', theme_save, name='profil_theme'),
    path('profil/aktivite/', activity_calendar_api, name='profil_aktivite'),
]

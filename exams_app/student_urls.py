from django.urls import path
from . import views

app_name = 'student'

urlpatterns = [
    path('', views.student_dashboard, name='dashboard'),
    path('analytics/', views.dashboard_analytics_partial, name='dashboard_analytics'),
    path('analytics/chart/', views.dashboard_chart_data, name='dashboard_chart_data'),
    path('denemeler/', views.denemeler_list, name='denemeler_list'),
    path('denemeler/cards/', views.denemeler_cards_partial, name='denemeler_cards'),
    path('denemeler/topics/', views.denemeler_topics_partial, name='denemeler_topics'),
    path('compare/', views.exam_compare, name='exam_compare'),
    path('karsilastir/', views.student_compare_exams, name='student_compare'),
    path('karsilastir/v2/', views.student_compare_v2, name='compare_v2'),
    path('exam/new/', views.exam_create_step1, name='exam_step1'),
    path('exam/new/v2/', views.exam_create_v2, name='exam_create_v2'),
    path('exam/<int:exam_id>/', views.student_exam_detail, name='exam_detail'),
    path('exam/<int:exam_id>/v2/', views.student_exam_detail_v2, name='exam_detail_v2'),
    path('exam/<int:exam_id>/edit/', views.exam_edit, name='exam_edit'),
    path('exam/<int:exam_id>/delete/', views.exam_delete, name='exam_delete'),
    path('exam/<int:exam_id>/errors/', views.exam_create_step2, name='exam_step2'),
    path('exam/<int:exam_id>/notes/', views.exam_notes_update, name='exam_notes_update'),
    path('exam/<int:exam_id>/result/<int:result_id>/', views.exam_result_update, name='exam_result_update'),
    path('task/<int:task_id>/complete/', views.complete_task, name='complete_task'),
    path('self-assign/', views.self_assign_task, name='self_assign_task'),
    path('task/<int:task_id>/action/', views.student_task_action, name='task_action'),
    # Branş Deneme
    path('brans/ekle/', views.brans_create,             name='brans_create'),
    path('brans/<int:pk>/', views.brans_detail,         name='brans_detail'),
    path('brans/<int:pk>/konular/', views.brans_topic_errors,   name='brans_topic_errors'),
    path('brans/<int:pk>/duzenle/', views.brans_edit,   name='brans_edit'),
    path('brans/<int:pk>/sil/', views.brans_delete,     name='brans_delete'),
    path('brans/<slug:subject_slug>/', views.brans_subject_detail_student, name='brans_subject_detail'),
]

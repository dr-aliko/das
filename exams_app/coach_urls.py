from django.urls import path
from . import views

app_name = 'coach'

urlpatterns = [
    path('', views.coach_dashboard, name='dashboard'),
    path('denemeler/', views.coach_exam_overview, name='exam_overview'),
    path('student/<int:student_id>/unlink/', views.unlink_student, name='unlink_student'),
    path('student/<int:student_id>/denemeler/', views.coach_student_exams, name='student_exams'),
    path('student/<int:student_id>/deneme/<int:exam_id>/', views.coach_student_exam_detail, name='student_exam_detail'),
    path('student/<int:student_id>/', views.coach_student_detail, name='student_detail'),
    path('student/<int:student_id>/brans/', views.brans_hub_coach, name='student_brans_hub'),
    path('student/<int:student_id>/brans/ekle/', views.coach_brans_create_for_student, name='student_brans_create'),
    path('student/<int:student_id>/brans/<slug:subject_slug>/', views.brans_subject_detail_coach, name='student_brans_subject_detail'),
    path('student/<int:student_id>/brans/<int:pk>/konular/', views.coach_brans_topic_errors, name='student_brans_topic_errors'),
    path('student/<int:student_id>/brans-task-assign/', views.coach_brans_task_assign, name='brans_task_assign'),
    path('student/<int:student_id>/brans-task-action/<int:task_id>/', views.coach_brans_task_action, name='brans_task_action'),
    path('student/<int:student_id>/compare/', views.compare_exams, name='compare_exams'),
    path('assign-task/', views.assign_task, name='assign_task'),
    path('task/<int:task_id>/complete/', views.coach_complete_task, name='complete_task'),
    path('task/<int:task_id>/action/', views.coach_task_action, name='task_action'),
    path('brans/', views.coach_brans_analytics, name='brans_analytics'),
    path('brans/student/<int:student_id>/', views.coach_brans_student_detail, name='brans_student_detail'),
    path('brans/student/<int:student_id>/karsilastir/', views.coach_brans_compare, name='brans_compare'),
]

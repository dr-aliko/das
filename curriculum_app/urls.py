from django.urls import path
from . import coach_views

app_name = 'curriculum'

urlpatterns = [
    path('', coach_views.macro_plan_list, name='list'),
    path('new/', coach_views.macro_plan_create, name='create'),
    path('<int:pk>/', coach_views.macro_plan_detail, name='detail'),
    path('<int:pk>/delete/', coach_views.macro_plan_delete, name='delete'),
    path('<int:pk>/regenerate/', coach_views.macro_plan_regenerate, name='regenerate'),
    path('student/<int:student_id>/set-exam-dates/', coach_views.set_student_exam_dates, name='set_exam_dates'),
]

from django.urls import path
from . import coach_views

app_name = 'curriculum'

urlpatterns = [
    path('', coach_views.macro_plan_list, name='list'),
    path('new/', coach_views.macro_plan_create, name='create'),
    path('<int:pk>/', coach_views.macro_plan_detail, name='detail'),
    path('<int:pk>/delete/', coach_views.macro_plan_delete, name='delete'),
    path('<int:pk>/regenerate/', coach_views.macro_plan_regenerate, name='regenerate'),
    path('<int:pk>/approve/', coach_views.macro_plan_approve, name='approve'),
    path('student/<int:student_id>/set-exam-dates/', coach_views.set_student_exam_dates, name='set_exam_dates'),
    path('student/<int:student_id>/editor/',         coach_views.macro_plan_editor,        name='editor'),
    path('plan/<int:pk>/topic/move/',                coach_views.editor_move_topic,        name='editor_move'),
    path('plan/<int:pk>/topic/skip/',                coach_views.editor_skip_topic,        name='editor_skip'),
    path('plan/<int:pk>/topic/unskip/',              coach_views.editor_unskip_topic,      name='editor_unskip'),
    path('plan/<int:pk>/generate-weekly/',           coach_views.macro_plan_to_weekly,     name='generate_weekly'),
]

from django.urls import path
from . import views

app_name = 'student_konu_takip'

urlpatterns = [
    path('', views.StudentKonuTakipView.as_view(), name='index'),
    path('toggle/', views.StudentToggleView.as_view(), name='toggle'),
]

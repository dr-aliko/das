from django.urls import path
from . import views

app_name = 'konu_takip'

urlpatterns = [
    path('', views.CoachKonuTakipView.as_view(), name='coach_index'),
    path('toggle/', views.CoachToggleView.as_view(), name='coach_toggle'),
]

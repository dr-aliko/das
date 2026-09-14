from django.urls import path
from . import views

app_name = 'konu_takip'

urlpatterns = [
    path('', views.CoachKonuTakipView.as_view(), name='coach_index'),
    path('toggle/', views.CoachToggleView.as_view(), name='coach_toggle'),
    path('api/', views.CoachKonuTakipApiView.as_view(), name='coach_api'),
    path('review/', views.CoachReviewView.as_view(), name='coach_review'),
    path('reviews/', views.CoachReviewsApiView.as_view(), name='coach_reviews_api'),
    path('schedule/', views.CoachAllReviewsApiView.as_view(), name='coach_schedule_api'),
    path('toggle-sr/', views.CoachToggleSrView.as_view(), name='coach_toggle_sr'),
]

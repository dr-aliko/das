from django.urls import path
from . import views

app_name = 'student_konu_takip'

urlpatterns = [
    path('', views.StudentKonuTakipView.as_view(), name='index'),
    path('toggle/', views.StudentToggleView.as_view(), name='toggle'),
    path('api/', views.StudentKonuTakipApiView.as_view(), name='api'),
    path('review/', views.StudentReviewView.as_view(), name='review'),
    path('reviews/', views.StudentReviewsApiView.as_view(), name='reviews_api'),
    path('schedule/', views.StudentAllReviewsApiView.as_view(), name='schedule_api'),
    path('toggle-sr/', views.StudentToggleSrView.as_view(), name='toggle_sr'),
]

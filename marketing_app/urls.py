from django.urls import path
from . import views

app_name = 'marketing'

urlpatterns = [
    path('', views.home, name='home'),
    path('ozellikler/', views.features, name='features'),
    path('fiyatlandirma/', views.pricing, name='pricing'),
    path('koclar/', views.coach_list, name='coach_list'),
    path('koclar/<slug:slug>/', views.coach_detail, name='coach_detail'),
    path('koclar/<slug:slug>/basvur/', views.coach_request, name='coach_request'),
    path('hakkimizda/', views.about, name='about'),
    path('iletisim/', views.contact, name='contact'),
]

from django.urls import path

from . import views

app_name = 'struggle'

urlpatterns = [
    path('', views.StudentStruggleIndexView.as_view(), name='index'),
    path('add/', views.StudentStruggleAddView.as_view(), name='add'),
    path('<int:pk>/delete/', views.StudentStruggleDeleteView.as_view(), name='delete'),
    path('review/', views.StudentStruggleReviewView.as_view(), name='review'),
    path('topics/', views.StudentStruggleTopicsApiView.as_view(), name='topics_api'),
]

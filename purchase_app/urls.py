from django.urls import path

from . import views

app_name = 'purchase'

urlpatterns = [
    path('<int:wp_id>/',                         views.purchase_page,   name='purchase_page'),
    path('<int:wp_id>/checkout/',                views.checkout,        name='checkout'),
    path('sandbox/pay/<uuid:order_token>/',      views.sandbox_pay,     name='sandbox_pay'),
    path('sandbox/confirm/<uuid:order_token>/',  views.sandbox_confirm, name='sandbox_confirm'),
    path('tesekkur/<uuid:order_token>/',         views.success,         name='success'),
]

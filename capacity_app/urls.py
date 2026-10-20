from django.urls import path
from . import views

app_name = 'capacity'

urlpatterns = [
    path('',                                     views.capacity_page,               name='page'),
    path('satin-al/<uuid:order_token>/',         views.capacity_order_instructions,  name='order_instructions'),
    path('satin-al/<uuid:order_token>/bildir/',  views.capacity_order_claim,         name='order_claim'),
]

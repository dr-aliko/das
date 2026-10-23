from django.urls import path
from . import views

app_name = 'capacity'

urlpatterns = [
    path('',                                           views.capacity_page,               name='page'),
    path('satin-al/<uuid:order_token>/',               views.capacity_order_instructions,  name='order_instructions'),
    path('satin-al/<uuid:order_token>/bildir/',        views.capacity_order_claim,         name='order_claim'),
    path('ogr-yenile/<int:cs_pk>/',                   views.renewal_start,               name='renewal_start'),
    path('yenile/<uuid:order_token>/',                 views.renewal_instructions,         name='renewal_instructions'),
    path('yenile/<uuid:order_token>/bildir/',          views.renewal_claim,                name='renewal_claim'),
]

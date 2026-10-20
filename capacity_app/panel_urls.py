from django.urls import path
from . import panel_views

app_name = 'capacity_panel'

urlpatterns = [
    path('',                                    panel_views.panel_capacity,                  name='overview'),
    path('siparis/<int:pk>/',                   panel_views.panel_capacity_order_detail,     name='order_detail'),
    path('siparis/<int:pk>/odeme-alindi/',      panel_views.panel_capacity_order_mark_paid,  name='order_mark_paid'),
    path('siparis/<int:pk>/iptal/',             panel_views.panel_capacity_order_cancel,     name='order_cancel'),
    path('grant/yeni/',                         panel_views.panel_capacity_grant_create,     name='grant_create'),
    path('grant/<int:pk>/duzenle/',             panel_views.panel_grant_adjust,              name='grant_adjust'),
    path('koc/<int:coach_pk>/grantlar/',        panel_views.panel_coach_grants,              name='coach_grants'),
    path('ayarlar/',                            panel_views.panel_capacity_settings,         name='settings'),
]

from django.urls import path

from . import views

app_name = 'purchase_panel'

urlpatterns = [
    path('siparisler/',                          views.panel_orders,           name='orders'),
    path('siparisler/<int:pk>/',                 views.panel_order_detail,     name='order_detail'),
    path('siparisler/<int:pk>/odeme-alindi/',    views.panel_order_mark_paid,  name='order_mark_paid'),
    path('siparisler/<int:pk>/iptal/',           views.panel_order_cancel,     name='order_cancel'),
    path('planlar/',                             views.panel_plans,            name='plans'),
    path('planlar/yeni/',                        views.panel_plan_create,      name='plan_create'),
    path('planlar/<int:pk>/guncelle/',           views.panel_plan_update,      name='plan_update'),
]

from django.urls import path

from . import views

app_name = 'earnings_panel'

urlpatterns = [
    path('',                                views.panel_kazanclar_list,      name='list'),
    path('export.csv',                      views.panel_kazanclar_export_csv, name='export_csv'),
    path('<int:pk>/onayla/',                views.panel_kazanclar_approve,   name='approve'),
    path('<int:pk>/odeme-alindi/',          views.panel_kazanclar_mark_paid, name='mark_paid'),
    path('<int:pk>/iptal/',                 views.panel_kazanclar_void,      name='void'),
    path('manuel-odeme/',                   views.panel_manuel_odeme_create, name='manuel_odeme'),
]

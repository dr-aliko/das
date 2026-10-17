from django.urls import path

from . import views

app_name = 'purchase'

urlpatterns = [
    path('<int:wp_id>/',                                views.step1,                      name='page'),
    path('<int:wp_id>/dogrula/',                        views.step2_verify,               name='verify'),
    path('<int:wp_id>/kod-tekrar/',                     views.step2_resend,               name='resend'),
    path('<int:wp_id>/odeme/',                          views.step3_payment,              name='payment'),
    path('sandbox/pay/<uuid:order_token>/',             views.sandbox_pay,                name='sandbox_pay'),
    path('sandbox/confirm/<uuid:order_token>/',         views.sandbox_confirm,            name='sandbox_confirm'),
    path('havale/<uuid:order_token>/',                  views.bank_transfer_instructions, name='bank_transfer_instructions'),
    path('tesekkur/<uuid:order_token>/',                views.success,                    name='success'),
]

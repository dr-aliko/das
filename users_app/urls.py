from django.urls import path
from . import views

app_name = 'users_app'

urlpatterns = [
    path('login/',              views.CustomLoginView.as_view(), name='login'),
    path('register/',           views.register_view,             name='register'),
    path('logout/',             views.logout_view,               name='logout'),
    path('awaiting-approval/',  views.awaiting_approval_view,    name='awaiting_approval'),
    path('invite-students/',    views.coach_invite_view,          name='coach_invites'),
    path('invite/<str:token>/', views.invite_register_view,       name='invite_register'),
    path('invite/<int:invite_id>/revoke/', views.revoke_invite,   name='revoke_invite'),
    path('inbox/',                        views.coach_inbox_api,  name='inbox_api'),
    path('inbox/<int:alert_id>/read/',    views.alert_mark_read,  name='alert_read'),
    path('inbox/<int:alert_id>/dismiss/', views.alert_dismiss,    name='alert_dismiss'),
    path('inbox/mark-all-read/',          views.alert_mark_all_read, name='alert_mark_all_read'),
]

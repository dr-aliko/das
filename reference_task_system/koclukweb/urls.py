from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("giris/", auth_views.LoginView.as_view(template_name="kocluk/giris.html"), name="login"),
    path("cikis/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("", include("kocluk.urls")),
]

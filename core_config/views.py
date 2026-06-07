from django.db import connections
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "HEAD"])
def healthz_view(request):
    try:
        connections['default'].cursor()
    except Exception:
        return JsonResponse({"status": "unhealthy", "database": "down"}, status=503)
    return JsonResponse({"status": "healthy", "database": "up"})


def app_root_view(request):
    if not request.user.is_authenticated:
        return redirect('users_app:login')
    if request.user.is_coach:
        return redirect('/coach/')
    return redirect('/student/')

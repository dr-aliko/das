from .context_processors import V2_COOKIE, DESKTOP_V2_COOKIE


class V2CookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, '_set_v2_cookie', False):
            response.set_cookie(V2_COOKIE, '1', max_age=60 * 60 * 24 * 365, samesite='Lax')
        if getattr(request, '_clear_v2_cookie', False):
            response.delete_cookie(V2_COOKIE)
        if getattr(request, '_set_desktop_v2_cookie', False):
            response.set_cookie(DESKTOP_V2_COOKIE, '1', max_age=60 * 60 * 24 * 365, samesite='Lax')
        if getattr(request, '_clear_desktop_v2_cookie', False):
            response.delete_cookie(DESKTOP_V2_COOKIE)
        return response

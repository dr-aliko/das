from django.conf import settings

V2_COOKIE = 'das_v2'
DESKTOP_V2_COOKIE = 'das_desktop_v2'


def v2_shell(request):
    if not getattr(settings, 'V2_SHELL_ENABLED', True):
        return {'v2_shell': False}

    qp = request.GET.get('v2')
    if qp == '1':
        request._set_v2_cookie = True
        enabled = True
    elif qp == '0':
        request._clear_v2_cookie = True
        enabled = False
    else:
        cookie_val = request.COOKIES.get(V2_COOKIE)
        if cookie_val is not None:
            enabled = cookie_val == '1'        # explicit cookie always wins
        else:
            enabled = getattr(settings, 'V2_DEFAULT', False)   # dev default

    return {'v2_shell': enabled}


def desktop_v2(request):
    if not getattr(settings, 'DESKTOP_V2_ENABLED', True):
        return {'desktop_v2': False}

    qp = request.GET.get('desktop_v2')
    if qp == '1':
        request._set_desktop_v2_cookie = True
        enabled = True
    elif qp == '0':
        request._clear_desktop_v2_cookie = True
        enabled = False
    else:
        cookie_val = request.COOKIES.get(DESKTOP_V2_COOKIE)
        if cookie_val is not None:
            enabled = cookie_val == '1'
        else:
            enabled = getattr(settings, 'DESKTOP_V2_DEFAULT', False)

    return {'desktop_v2': enabled}


def site_urls(request):
    return {
        'PUBLIC_SITE_URL': settings.PUBLIC_SITE_URL,
        'APP_BASE_URL': settings.APP_BASE_URL,
    }

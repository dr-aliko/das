from django import template
from django.utils.safestring import mark_safe

register = template.Library()

_STYLE = {
    'expired': 'color:#f87171;font-size:11px;white-space:nowrap;',
    'warning': 'color:#fbbf24;font-size:11px;white-space:nowrap;',
    'normal':  'color:#94a3b8;font-size:11px;white-space:nowrap;',
}


@register.simple_tag
def membership_badge(cs):
    from users_app.utils import membership_expiry_info
    info = membership_expiry_info(cs)
    if not info:
        return ''
    style = _STYLE.get(info['variant'], _STYLE['normal'])
    return mark_safe(
        f'<span style="{style}" title="{info["title"]}">{info["label"]}</span>'
    )

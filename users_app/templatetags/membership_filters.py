from django import template
from django.utils.safestring import mark_safe

register = template.Library()

_CLASS = {
    'success': 'das-badge das-badge--success',
    'warn':    'das-badge das-badge--warn',
    'danger':  'das-badge das-badge--danger',
}


@register.simple_tag
def membership_badge(cs):
    from users_app.utils import membership_expiry_info
    info = membership_expiry_info(cs)
    if not info:
        return ''
    cls = _CLASS.get(info['variant'], _CLASS['warn'])
    return mark_safe(
        f'<span class="{cls}" title="{info["title"]}" style="font-weight:600">'
        f'{info["label"]}</span>'
    )

from django import template

register = template.Library()


@register.filter
def kurus_tl(value):
    """
    Format an integer kuruş value as whole Turkish TL (floor to TL, no decimal part).
    83300  → "833 ₺"
    250000 → "2.500 ₺"
    -5000  → "-50 ₺"
    Odd kuruş are silently floored: 83333 → "833 ₺"
    """
    try:
        kurus = int(value)
    except (TypeError, ValueError):
        return value

    sign = '-' if kurus < 0 else ''
    tl = abs(kurus) // 100
    tl_str = f'{tl:,}'.replace(',', '.')
    return f'{sign}{tl_str} ₺'


@register.filter
def kurus_to_tl_input(value):
    """Return kuruş as a whole-TL integer string for use in <input value="...">. 250000 → "2500"."""
    try:
        return str(int(value) // 100)
    except (TypeError, ValueError):
        return '0'

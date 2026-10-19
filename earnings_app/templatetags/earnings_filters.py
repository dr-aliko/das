from django import template

register = template.Library()


@register.filter
def kurus_tl(value):
    """
    Format an integer kuruş value as Turkish TL with exact cents.
    83333  → "833,33 ₺"
    166667 → "1.666,67 ₺"
    250000 → "2.500,00 ₺"
    Handles negative values (adjustments): -5000 → "-50,00 ₺"
    """
    try:
        kurus = int(value)
    except (TypeError, ValueError):
        return value

    sign = '-' if kurus < 0 else ''
    kurus_abs = abs(kurus)
    tl = kurus_abs // 100
    kr = kurus_abs % 100
    tl_str = f'{tl:,}'.replace(',', '.')
    return f'{sign}{tl_str},{kr:02d} ₺'


@register.filter
def kurus_to_tl_input(value):
    """Return kuruş as a decimal TL string for use in <input value="...">. 250000 → "2500.00"."""
    try:
        return f'{int(value) / 100:.2f}'
    except (TypeError, ValueError):
        return '0.00'

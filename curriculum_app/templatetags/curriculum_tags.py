from django import template

register = template.Library()


@register.filter
def get(dictionary, key):
    """Return dictionary[key], or None if missing. Usage: {{ dict|get:key }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

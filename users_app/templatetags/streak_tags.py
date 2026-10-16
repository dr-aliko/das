from django import template
from users_app.services.streak_engine import effective_streak as _effective_streak

register = template.Library()


@register.filter
def effective_streak(user):
    return _effective_streak(user)

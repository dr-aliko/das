"""
Tests for the effective_streak display helper.

effective_streak(user, today=None) must:
  - return 0 when last_activity_date is None
  - return 0 when last_activity_date is two or more days before today
  - return current_streak when last_activity_date is yesterday
  - return current_streak when last_activity_date is today
  - respect the Europe/Istanbul timezone boundary
"""
from datetime import date, timedelta

from users_app.services.streak_engine import effective_streak


class _User:
    """Minimal stand-in — no DB needed."""
    def __init__(self, current_streak, last_activity_date):
        self.current_streak = current_streak
        self.last_activity_date = last_activity_date


_TODAY = date(2024, 3, 16)
_YESTERDAY = _TODAY - timedelta(days=1)   # 2024-03-15
_TWO_AGO = _TODAY - timedelta(days=2)     # 2024-03-14


def test_none_last_activity_returns_zero():
    u = _User(current_streak=5, last_activity_date=None)
    assert effective_streak(u, today=_TODAY) == 0


def test_two_days_ago_returns_zero():
    u = _User(current_streak=5, last_activity_date=_TWO_AGO)
    assert effective_streak(u, today=_TODAY) == 0


def test_yesterday_returns_stored_streak():
    u = _User(current_streak=7, last_activity_date=_YESTERDAY)
    assert effective_streak(u, today=_TODAY) == 7


def test_today_returns_stored_streak():
    u = _User(current_streak=3, last_activity_date=_TODAY)
    assert effective_streak(u, today=_TODAY) == 3


def test_zero_stored_streak_with_valid_date():
    # Edge case: stored value is 0 but last date is valid — return as-is.
    u = _User(current_streak=0, last_activity_date=_YESTERDAY)
    assert effective_streak(u, today=_TODAY) == 0


# ── Istanbul day-boundary tests ───────────────────────────────────────────────

def test_istanbul_boundary_23_30():
    """
    Student last active at 23:30 Istanbul on March 15.
    The Istanbul date is 2024-03-15 = yesterday → streak is live.
    """
    istanbul_last = date(2024, 3, 15)   # 23:30 Istanbul is still March 15
    u = _User(current_streak=4, last_activity_date=istanbul_last)
    assert effective_streak(u, today=date(2024, 3, 16)) == 4


def test_istanbul_boundary_00_30():
    """
    Student last active at 00:30 Istanbul on March 16 (= 21:30 UTC March 15).
    The Istanbul date stored is 2024-03-16 = today → streak is live.
    """
    istanbul_last = date(2024, 3, 16)   # 00:30 Istanbul = March 16
    u = _User(current_streak=4, last_activity_date=istanbul_last)
    assert effective_streak(u, today=date(2024, 3, 16)) == 4


def test_far_past_returns_zero():
    """A student who hasn't studied in months shows 0."""
    u = _User(current_streak=42, last_activity_date=date(2024, 1, 1))
    assert effective_streak(u, today=_TODAY) == 0

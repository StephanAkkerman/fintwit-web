from unittest.mock import patch

import pandas as pd

from app.services.market_hours_service import _session_info


class _RegularHolidayCalendar:
    def holidays(self, start=None, end=None, return_name=False):
        if return_name:
            return pd.Series(
                ["Christmas Day"],
                index=[pd.Timestamp("2026-12-25")],
            )
        return pd.DatetimeIndex([pd.Timestamp("2026-12-25")])


class _HolidayClosedCalendar:
    regular_holidays = _RegularHolidayCalendar()
    adhoc_holidays = []

    def is_open_at_time(self, now):
        return False

    def is_session(self, session_date):
        return False

    def next_open(self, now):
        return pd.Timestamp("2026-12-26T14:30:00+00:00")


class _WeekendClosedCalendar:
    regular_holidays = None
    adhoc_holidays = []

    def is_open_at_time(self, now):
        return False

    def is_session(self, session_date):
        return False

    def next_open(self, now):
        return pd.Timestamp("2026-12-28T14:30:00+00:00")


def test_session_info_marks_holiday_closure():
    now_utc = pd.Timestamp("2026-12-25T15:00:00+00:00")

    with patch(
        "app.services.market_hours_service.xcals.get_calendar",
        return_value=_HolidayClosedCalendar(),
    ):
        info = _session_info("XNYS", "America/New_York", now_utc)

    assert info["session"] == "Closed"
    assert info["closure_reason"] == "holiday"
    assert info["is_holiday"] is True
    assert info["holiday_name"] == "Christmas Day"


def test_session_info_marks_weekend_closure():
    now_utc = pd.Timestamp("2026-12-27T15:00:00+00:00")

    with patch(
        "app.services.market_hours_service.xcals.get_calendar",
        return_value=_WeekendClosedCalendar(),
    ):
        info = _session_info("XNYS", "America/New_York", now_utc)

    assert info["session"] == "Closed"
    assert info["closure_reason"] == "weekend"
    assert info["is_holiday"] is False
    assert info["holiday_name"] is None

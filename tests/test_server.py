"""Tests for the MCP tool functions (server.py)."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from mcp_calendar.ics import CalendarError
from mcp_calendar.server import list_calendars, list_events

WORK_URL = "https://example.com/work.ics"
HOME_URL = "https://example.com/home.ics"


def _ics_with_event_tomorrow(summary: str) -> bytes:
    """One VEVENT starting ~24h from now, so it always falls inside a
    short days_ahead window regardless of when the test suite runs."""
    start = datetime.now(timezone.utc) + timedelta(hours=24)
    end = start + timedelta(hours=1)
    fmt = "%Y%m%dT%H%M%SZ"
    return (
        "BEGIN:VCALENDAR\r\n"
        "PRODID:-//Test//Test//EN\r\n"
        "VERSION:2.0\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{summary}@test\r\n"
        f"DTSTAMP:{start.strftime(fmt)}\r\n"
        f"DTSTART:{start.strftime(fmt)}\r\n"
        f"DTEND:{end.strftime(fmt)}\r\n"
        f"SUMMARY:{summary}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode()


@pytest.fixture
def two_calendars(monkeypatch):
    monkeypatch.setenv(
        "CALENDAR_URLS",
        f'{{"Work": "{WORK_URL}", "Home": "{HOME_URL}"}}',
    )


def test_list_calendars_returns_sorted_names(two_calendars):
    assert list_calendars() == ["Home", "Work"]


def test_list_calendars_empty_when_unconfigured(monkeypatch):
    monkeypatch.delenv("CALENDAR_URLS", raising=False)
    monkeypatch.delenv("CALENDAR_ICS_URL", raising=False)
    assert list_calendars() == []


def test_list_events_no_calendars_raises(monkeypatch):
    monkeypatch.delenv("CALENDAR_URLS", raising=False)
    monkeypatch.delenv("CALENDAR_ICS_URL", raising=False)
    with pytest.raises(CalendarError, match="No calendar configured"):
        list_events()


@respx.mock
def test_list_events_unknown_calendar_raises(two_calendars):
    respx.get(WORK_URL).mock(
        return_value=httpx.Response(200, content=_ics_with_event_tomorrow("W"))
    )
    respx.get(HOME_URL).mock(
        return_value=httpx.Response(200, content=_ics_with_event_tomorrow("H"))
    )
    with pytest.raises(CalendarError, match="Unknown calendar"):
        list_events(calendar="Nonexistent")


@respx.mock
def test_list_events_merges_all_calendars(two_calendars):
    respx.get(WORK_URL).mock(
        return_value=httpx.Response(200, content=_ics_with_event_tomorrow("Work meeting"))
    )
    respx.get(HOME_URL).mock(
        return_value=httpx.Response(200, content=_ics_with_event_tomorrow("Home task"))
    )
    events = list_events(days_ahead=2)
    assert {e["calendar"] for e in events} == {"Work", "Home"}
    assert {e["summary"] for e in events} == {"Work meeting", "Home task"}


@respx.mock
def test_list_events_filters_to_one_calendar(two_calendars):
    respx.get(WORK_URL).mock(
        return_value=httpx.Response(200, content=_ics_with_event_tomorrow("Work meeting"))
    )
    events = list_events(calendar="Work", days_ahead=2)
    assert all(e["calendar"] == "Work" for e in events)
    assert len(events) == 1


@respx.mock
def test_list_events_respects_days_ahead_window(two_calendars):
    respx.get(WORK_URL).mock(
        return_value=httpx.Response(200, content=_ics_with_event_tomorrow("Work meeting"))
    )
    # event is ~24h out, a 0-day window should not include it
    events = list_events(calendar="Work", days_ahead=0)
    assert events == []

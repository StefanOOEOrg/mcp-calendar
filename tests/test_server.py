"""Tests for the MCP tool functions (server.py)."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from mcp_calendar.ics import CalendarError
from mcp_calendar.server import day_agenda, list_calendars, list_events

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


def _ics(*events: str) -> bytes:
    """A calendar from VEVENT bodies (DTSTART/DTEND/SUMMARY lines)."""
    body = "".join(f"BEGIN:VEVENT\r\nUID:{i}@test\r\nDTSTAMP:20261001T000000Z\r\n{ev}"
                   "END:VEVENT\r\n" for i, ev in enumerate(events))
    return ("BEGIN:VCALENDAR\r\nPRODID:-//Test//Test//EN\r\nVERSION:2.0\r\n" + body
            + "END:VCALENDAR\r\n").encode()


@respx.mock
def test_day_agenda_lines(monkeypatch):
    """All-day first, timed by start with overlaps, birthdays, TV last; other days left out."""
    monkeypatch.setenv("CALENDAR_URLS", '{"Work": "https://example.com/w.ics", '
                       '"Geburtstage": "https://example.com/b.ics", '
                       '"TV Sport": "https://example.com/tv.ics"}')
    respx.get("https://example.com/w.ics").mock(return_value=httpx.Response(200, content=_ics(
        "DTSTART;TZID=Europe/Vienna:20261023T100000\r\nDTEND;TZID=Europe/Vienna:20261023T113000\r\n"
        "SUMMARY:Review\r\nLOCATION:Office\r\n",
        "DTSTART;TZID=Europe/Vienna:20261023T090000\r\nDTEND;TZID=Europe/Vienna:20261023T103000\r\n"
        "SUMMARY:Standup\r\n",
        "DTSTART;VALUE=DATE:20261022\r\nDTEND;VALUE=DATE:20261025\r\nSUMMARY:Messe\r\n",
        "DTSTART;TZID=Europe/Vienna:20261024T090000\r\nDTEND;TZID=Europe/Vienna:20261024T100000\r\n"
        "SUMMARY:Tomorrow\r\n")))
    respx.get("https://example.com/b.ics").mock(return_value=httpx.Response(200, content=_ics(
        "DTSTART;VALUE=DATE:20261023\r\nDTEND;VALUE=DATE:20261024\r\nSUMMARY:Anna\r\n")))
    respx.get("https://example.com/tv.ics").mock(return_value=httpx.Response(200, content=_ics(
        "DTSTART;TZID=Europe/Vienna:20261023T200000\r\nDTEND;TZID=Europe/Vienna:20261023T220000\r\n"
        "SUMMARY:Hockey\r\n")))

    assert day_agenda("2026-10-23").splitlines() == [
        "📅 Termine Fr 23.10.",
        "• ganztägig: Messe (bis 24.10.) · Work",
        "• 09:00–10:30 Standup · Work ⚠ überschneidet sich mit Review",
        "• 10:00–11:30 Review (Office) · Work ⚠ überschneidet sich mit Standup",
        "🎂 Anna",
        "• 20:00–22:00 Hockey · TV Sport",
    ]


@respx.mock
def test_day_agenda_empty_day(two_calendars):
    respx.get(WORK_URL).mock(return_value=httpx.Response(200, content=_ics()))
    respx.get(HOME_URL).mock(return_value=httpx.Response(200, content=_ics()))
    assert day_agenda("2026-10-23") == "📅 Termine Fr 23.10.\nKeine Termine."

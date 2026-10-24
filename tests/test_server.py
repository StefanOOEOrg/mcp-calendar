"""Tests for the MCP tool functions (server.py)."""
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from mcp_calendar.server import (
    create_event_invite,
    day_agenda,
    list_calendars,
    list_events,
)

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
    with pytest.raises(ToolError, match="No calendar configured"):
        list_events()


@respx.mock
def test_list_events_unknown_calendar_raises(two_calendars):
    respx.get(WORK_URL).mock(
        return_value=httpx.Response(200, content=_ics_with_event_tomorrow("W"))
    )
    respx.get(HOME_URL).mock(
        return_value=httpx.Response(200, content=_ics_with_event_tomorrow("H"))
    )
    with pytest.raises(ToolError, match="Unknown calendar"):
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
                       '"Birthdays": "https://example.com/b.ics", '
                       '"TV Sport": "https://example.com/tv.ics"}')
    respx.get("https://example.com/w.ics").mock(return_value=httpx.Response(200, content=_ics(
        "DTSTART;TZID=Europe/Vienna:20261023T100000\r\nDTEND;TZID=Europe/Vienna:20261023T113000\r\n"
        "SUMMARY:Review\r\nLOCATION:Office\r\n",
        "DTSTART;TZID=Europe/Vienna:20261023T090000\r\nDTEND;TZID=Europe/Vienna:20261023T103000\r\n"
        "SUMMARY:Standup\r\n",
        "DTSTART;VALUE=DATE:20261022\r\nDTEND;VALUE=DATE:20261025\r\nSUMMARY:Trade fair\r\n",
        "DTSTART;TZID=Europe/Vienna:20261024T090000\r\nDTEND;TZID=Europe/Vienna:20261024T100000\r\n"
        "SUMMARY:Tomorrow\r\n")))
    respx.get("https://example.com/b.ics").mock(return_value=httpx.Response(200, content=_ics(
        "DTSTART;VALUE=DATE:20261023\r\nDTEND;VALUE=DATE:20261024\r\nSUMMARY:Anna\r\n")))
    respx.get("https://example.com/tv.ics").mock(return_value=httpx.Response(200, content=_ics(
        "DTSTART;TZID=Europe/Vienna:20261023T200000\r\nDTEND;TZID=Europe/Vienna:20261023T220000\r\n"
        "SUMMARY:Hockey\r\n")))

    assert day_agenda("2026-10-23", language="de").splitlines() == [
        "📅 Termine Fr 23.10.",
        "• ganztägig: Trade fair (bis 24.10.) · Work",
        "• 09:00–10:30 Standup · Work ⚠ überschneidet sich mit Review",
        "• 10:00–11:30 Review (Office) · Work ⚠ überschneidet sich mit Standup",
        "🎂 Anna",
        "• 20:00–22:00 Hockey · TV Sport",
    ]
    assert day_agenda("2026-10-23").splitlines()[1:3] == [
        "• all day: Trade fair (until 24.10.) · Work",
        "• 09:00–10:30 Standup · Work ⚠ overlaps with Review",
    ]


@respx.mock
def test_day_agenda_empty_day(two_calendars):
    respx.get(WORK_URL).mock(return_value=httpx.Response(200, content=_ics()))
    respx.get(HOME_URL).mock(return_value=httpx.Response(200, content=_ics()))
    assert day_agenda("2026-10-23") == "📅 Events Fri 23.10.\nNo events."
    assert day_agenda("2026-10-23", language="de") == "📅 Termine Fr 23.10.\nKeine Termine."


# --- Fehlerpfade (Issue #1, WP1) -------------------------------------------
# Jeder Fachfehler muss als ToolError beim Client ankommen; eine rohe
# CalendarError/ValueError/ZoneInfoNotFoundError wird vom SDK zu
# "Error executing tool <name>" ohne Ursache.


def test_broken_config_raises_tool_error(monkeypatch):
    monkeypatch.setenv("CALENDAR_URLS", "{not json")
    with pytest.raises(ToolError, match="not valid JSON"):
        list_calendars()
    with pytest.raises(ToolError, match="not valid JSON"):
        list_events()


def test_unknown_timezone_raises_tool_error(two_calendars, monkeypatch):
    monkeypatch.setenv("CALENDAR_TIMEZONE", "Atlantis/City")
    with pytest.raises(ToolError, match="Unknown timezone 'Atlantis/City'"):
        list_events()
    with pytest.raises(ToolError, match="CALENDAR_TIMEZONE"):
        day_agenda("2026-10-23")


def test_invalid_day_raises_tool_error(two_calendars):
    with pytest.raises(ToolError, match="day must be YYYY-MM-DD"):
        day_agenda("2026-13-45")
    with pytest.raises(ToolError, match="day must be YYYY-MM-DD"):
        day_agenda("morgen")


@respx.mock
def test_fetch_error_raises_tool_error(two_calendars):
    respx.get(WORK_URL).mock(return_value=httpx.Response(500))
    respx.get(HOME_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(ToolError, match="Failed to fetch calendar"):
        list_events()


def test_invite_title_with_line_break_raises_tool_error(monkeypatch):
    monkeypatch.setenv("CALENDAR_INVITE_TO", "me@example.com")
    monkeypatch.setenv("CALENDAR_HIMALAYA", "/bin/true")
    with pytest.raises(ToolError, match="title must not contain line breaks"):
        create_event_invite("Zeile1\nZeile2", "2026-10-17T14:00")


def test_invite_mail_failure_raises_tool_error(monkeypatch):
    monkeypatch.setenv("CALENDAR_INVITE_TO", "me@example.com")
    monkeypatch.setenv("CALENDAR_HIMALAYA", "/bin/false")
    with pytest.raises(ToolError, match="himalaya failed"):
        create_event_invite("Zahnarzt", "2026-10-17T14:00")


def test_ambient_calendar_env_is_ignored():
    """Die conftest-Fixture pinnt die Zeitzone — sonst hängt die Suite am Rechner."""
    assert os.environ.get("CALENDAR_TIMEZONE") == "Europe/Vienna"

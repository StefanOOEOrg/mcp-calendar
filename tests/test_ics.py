"""Tests for ICS fetching/parsing (ics.py)."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from mcp_calendar.ics import CalendarError, events_in_range

FIXTURE = (Path(__file__).parent / "fixtures" / "sample.ics").read_bytes()
URL = "https://example.com/calendar.ics"
TZ = ZoneInfo("Europe/Vienna")


@respx.mock
def _events(start: datetime, end: datetime):
    respx.get(URL).mock(return_value=httpx.Response(200, content=FIXTURE))
    return events_in_range(URL, start=start, end=end, tz_name="Europe/Vienna")


def test_single_event_returned():
    events = _events(
        datetime(2026, 1, 1, tzinfo=TZ), datetime(2026, 1, 31, tzinfo=TZ)
    )
    titles = [e["summary"] for e in events]
    assert "Standup" in titles


def test_recurring_event_expands_to_all_occurrences():
    events = _events(
        datetime(2026, 1, 1, tzinfo=TZ), datetime(2026, 1, 31, tzinfo=TZ)
    )
    syncs = [e for e in events if e["summary"] == "Weekly Sync"]
    assert len(syncs) == 3  # RRULE COUNT=3


def test_all_day_event_flagged():
    events = _events(
        datetime(2026, 1, 1, tzinfo=TZ), datetime(2026, 1, 31, tzinfo=TZ)
    )
    holiday = next(e for e in events if e["summary"] == "Holiday")
    assert holiday["all_day"] is True


def test_events_sorted_by_start():
    events = _events(
        datetime(2026, 1, 1, tzinfo=TZ), datetime(2026, 1, 31, tzinfo=TZ)
    )
    starts = [e["start"] for e in events]
    assert starts == sorted(starts)


def test_range_excludes_events_outside_window():
    events = _events(
        datetime(2026, 1, 7, tzinfo=TZ), datetime(2026, 1, 8, tzinfo=TZ)
    )
    assert all(e["summary"] != "Standup" for e in events)  # Jan 5, outside


def test_location_and_description_included():
    events = _events(
        datetime(2026, 1, 1, tzinfo=TZ), datetime(2026, 1, 31, tzinfo=TZ)
    )
    standup = next(e for e in events if e["summary"] == "Standup")
    assert standup["location"] == "Room 1"
    assert standup["description"] == "Daily standup"


@respx.mock
def test_fetch_error_raises_calendar_error():
    respx.get(URL).mock(return_value=httpx.Response(500))
    with pytest.raises(CalendarError):
        events_in_range(
            URL,
            start=datetime(2026, 1, 1, tzinfo=TZ),
            end=datetime(2026, 1, 31, tzinfo=TZ),
        )


@respx.mock
def test_malformed_ics_raises_calendar_error():
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"not an ics file"))
    with pytest.raises(CalendarError):
        events_in_range(
            URL,
            start=datetime(2026, 1, 1, tzinfo=TZ),
            end=datetime(2026, 1, 31, tzinfo=TZ),
        )

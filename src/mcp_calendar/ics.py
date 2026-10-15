"""Fetch and parse an ICS calendar, expanding recurring events."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from . import config


class CalendarError(RuntimeError):
    pass


def _fetch_raw(url: str) -> bytes:
    try:
        resp = httpx.get(url, timeout=config.fetch_timeout(), follow_redirects=True)
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPError as exc:
        raise CalendarError(f"Failed to fetch calendar: {exc}") from None


def _to_local(value, tz: ZoneInfo) -> tuple[datetime, bool]:
    """Normalize a VEVENT DTSTART/DTEND value to an aware local datetime.

    Returns (datetime, all_day). All-day events (a bare ``date``) are
    anchored at midnight local time.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.astimezone(tz), False
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=tz), True
    raise CalendarError(f"Unsupported DTSTART/DTEND type: {type(value)!r}")


def events_in_range(
    url: str, *, start: datetime, end: datetime, tz_name: str | None = None
) -> list[dict]:
    """Return events overlapping [start, end), expanded across recurrence rules,
    sorted by start time. Each event: name, start, end, all_day, location,
    description (trimmed)."""
    tz = ZoneInfo(tz_name or config.timezone())
    raw = _fetch_raw(url)
    try:
        cal = icalendar.Calendar.from_ical(raw)
    except ValueError as exc:
        raise CalendarError(f"Failed to parse ICS: {exc}") from None

    occurrences = recurring_ical_events.of(cal).between(start, end)

    out: list[dict] = []
    for ev in occurrences:
        dtstart = ev.get("DTSTART").dt
        dtend_prop = ev.get("DTEND")
        dtstart_local, all_day = _to_local(dtstart, tz)
        if dtend_prop is not None:
            dtend_local, _ = _to_local(dtend_prop.dt, tz)
        else:
            dtend_local = dtstart_local + timedelta(hours=1)

        summary = str(ev.get("SUMMARY", "(kein Titel)"))
        location = str(ev.get("LOCATION", "") or "")
        description = str(ev.get("DESCRIPTION", "") or "")
        if len(description) > 300:
            description = description[:300].rstrip() + "…"

        out.append({
            "summary": summary,
            "start": dtstart_local.isoformat(),
            "end": dtend_local.isoformat(),
            "all_day": all_day,
            "location": location,
            "description": description,
        })

    out.sort(key=lambda e: e["start"])
    return out

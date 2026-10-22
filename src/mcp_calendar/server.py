"""MCP server exposing read-only, on-demand queries against ICS calendar
share links (e.g. Proton Calendar's public 'share with anyone' link)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from mcp.server import MCPServer

from . import config
from .ics import CalendarError, events_in_range
from .invite import create_invite

mcp = MCPServer(
    "mcp-calendar",
    version="0.1.0",
    instructions=(
        "Calendar lookup against ICS share links (e.g. Proton Calendar's "
        "public link), on-demand only, no background polling. Use "
        "list_calendars() to see configured calendar names, then "
        "list_events(days_ahead=N) for upcoming events across all of them "
        "(or calendar=<name> for just one); day_agenda(day) gives one day as "
        "ready-made briefing lines. Where create_event_invite is "
        "offered, new appointments are sent as a mail invitation that the "
        "user accepts in his mailbox; there is no direct write access."
    ),
)


@mcp.tool()
def list_calendars() -> list[str]:
    """List the names of configured calendars (pass one as `calendar` to
    list_events to filter to just that calendar)."""
    return sorted(config.calendars().keys())


@mcp.tool()
def list_events(days_ahead: int = 7, calendar: str | None = None) -> list[dict]:
    """List events starting from now through `days_ahead` days out (default 7),
    across all configured calendars unless `calendar` names one specific
    calendar (see list_calendars()). Each event has: calendar, summary,
    start, end (ISO 8601, local time), all_day, location, description."""
    cals = config.calendars()
    if not cals:
        raise CalendarError(
            "No calendar configured — set CALENDAR_URLS or CALENDAR_ICS_URL."
        )
    if calendar is not None and calendar not in cals:
        raise CalendarError(
            f"Unknown calendar {calendar!r}. Known: {sorted(cals)}"
        )
    targets = {calendar: cals[calendar]} if calendar else cals

    tz = ZoneInfo(config.timezone())
    start = datetime.now(tz)
    end = start + timedelta(days=days_ahead)

    out: list[dict] = []
    for name, url in targets.items():
        for ev in events_in_range(url, start=start, end=end):
            out.append({"calendar": name, **ev})
    out.sort(key=lambda e: e["start"])
    return out


TEXTS = {
    "en": {"weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "events": "Events",
           "none": "No events.", "all_day": "all day", "until": "until",
           "overlaps": "overlaps with"},
    "de": {"weekdays": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"], "events": "Termine",
           "none": "Keine Termine.", "all_day": "ganztägig", "until": "bis",
           "overlaps": "überschneidet sich mit"},
}
BIRTHDAY_CALENDARS = ("geburtstag", "birthday")
LAST_CALENDARS = ("tv",)          # listed after everything else (TV listings)


def _agenda_line(ev: dict, others: list[dict], day: date, text: dict) -> str:
    start, end = datetime.fromisoformat(ev["start"]), datetime.fromisoformat(ev["end"])
    place = f" ({ev['location']})" if ev["location"] else ""
    if ev["all_day"]:
        last = (end - timedelta(days=1)).date()
        until = f" ({text['until']} {last:%d.%m.})" if last > day else ""
        return f"• {text['all_day']}: {ev['summary']}{place}{until} · {ev['calendar']}"
    clash = [o["summary"] for o in others
             if o is not ev and not o["all_day"]
             and datetime.fromisoformat(o["start"]) < end
             and start < datetime.fromisoformat(o["end"])]
    warn = f" ⚠ {text['overlaps']} {', '.join(clash)}" if clash else ""
    begin = f"{start:%H:%M}" if start.date() == day else f"{start:%d.%m. %H:%M}"
    finish = f"{end:%H:%M}" if end.date() == day else f"{end:%d.%m. %H:%M}"
    return f"• {begin}–{finish} {ev['summary']}{place} · {ev['calendar']}{warn}"


@mcp.tool()
def day_agenda(day: str | None = None, language: Literal["en", "de"] = "en") -> str:
    """One day's events (default today) across all calendars as ready-made briefing lines:
    all-day first, then by time with overlaps marked ⚠, birthdays as 🎂 lines, TV listings
    last. `day` is YYYY-MM-DD, `language` en or de. Copy the lines as they are."""
    text = TEXTS[language]
    tz = ZoneInfo(config.timezone())
    wanted = date.fromisoformat(day) if day else datetime.now(tz).date()
    start = datetime.combine(wanted, time.min, tzinfo=tz)
    if not config.calendars():
        raise CalendarError("No calendar configured — set CALENDAR_URLS or CALENDAR_ICS_URL.")
    events = []
    for name, url in config.calendars().items():
        events += [{"calendar": name, **ev}
                   for ev in events_in_range(url, start=start, end=start + timedelta(days=1))]

    def kind(ev: dict) -> int:
        name = ev["calendar"].lower()
        if any(word in name for word in BIRTHDAY_CALENDARS):
            return 1
        return 2 if any(name.startswith(word) for word in LAST_CALENDARS) else 0

    regular = sorted((ev for ev in events if kind(ev) == 0),
                     key=lambda ev: (not ev["all_day"], ev["start"]))
    lines = [_agenda_line(ev, regular, wanted, text) for ev in regular]
    lines += [f"🎂 {ev['summary']}" for ev in events if kind(ev) == 1]
    lines += [_agenda_line(ev, [], wanted, text) for ev in sorted(
        (ev for ev in events if kind(ev) == 2), key=lambda ev: ev["start"])]
    header = f"📅 {text['events']} {text['weekdays'][wanted.weekday()]} {wanted:%d.%m.}"
    return "\n".join([header, *(lines or [text["none"]])])


def create_event_invite(
    title: str,
    start: str,
    duration_minutes: int = 60,
    all_day: bool = False,
    days: int = 1,
    location: str | None = None,
    description: str | None = None,
) -> dict:
    """Add an event to the user's calendar: mails them a calendar invitation that
    they accept with one click (the calendar itself has no write access).
    Only when they explicitly ask for an appointment to be created. `start` is local
    time in ISO 8601, e.g. '2026-10-17T14:00' (or '2026-10-17' with all_day=True;
    `days` = number of days of an all-day event). Afterwards tell them the invitation
    is in their mailbox and has to be accepted there."""
    return create_invite(title, start, duration_minutes=duration_minutes,
                         all_day=all_day, days=days, location=location,
                         description=description)


# Offered only where a recipient is configured (CALENDAR_INVITE_TO).
if config.invite_to():
    mcp.tool()(create_event_invite)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

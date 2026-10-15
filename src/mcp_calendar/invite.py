"""Calendar invitations by mail: the way to *add* an event to a calendar that
has no write API (Proton Calendar).

An iCalendar PUBLISH (an event that needs no reply, like a booking
confirmation) is mailed through the ``himalaya`` CLI of the runtime user to
``CALENDAR_INVITE_TO``; Proton Mail shows "Add to Proton Calendar" for it.
A REQUEST from the user's own address to himself shows no such button.
"""

from __future__ import annotations

import subprocess
import uuid
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from zoneinfo import ZoneInfo

import icalendar

from . import config
from .ics import CalendarError

PRODID = "-//mcp-calendar//invite//DE"


def parse_start(value: str, all_day: bool, tz: ZoneInfo) -> datetime | date:
    """'2026-10-17T14:00' → aware local datetime; with all_day a date."""
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise CalendarError(
            f"start {value!r} is not ISO 8601 (e.g. 2026-10-17T14:00 or 2026-10-17)"
        ) from None
    if all_day:
        return parsed.date()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def build_invite(
    summary: str,
    start: datetime | date,
    end: datetime | date,
    location: str | None = None,
    description: str | None = None,
) -> bytes:
    """The iCalendar (METHOD:PUBLISH) of one event."""
    cal = icalendar.Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    event = icalendar.Event()
    event.add("uid", f"{uuid.uuid4()}@mcp-calendar")
    event.add("dtstamp", datetime.now(ZoneInfo("UTC")))
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add("summary", summary)
    event.add("sequence", 0)
    event.add("status", "CONFIRMED")
    if location:
        event.add("location", location)
    if description:
        event.add("description", description)
    cal.add_component(event)
    cal.add_missing_timezones()
    return cal.to_ical()


def build_mail(sender: str, to: str, summary: str, when: str, ics: bytes) -> bytes:
    """Text part + exactly one calendar attachment (text/calendar; method=PUBLISH)."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = f"Termin: {summary} ({when})"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="mcp-calendar.local")
    msg.set_content(f"{summary}\n{when}\n\nUse 'Add to calendar' to import it.\n")
    msg.add_attachment(ics, maintype="text", subtype="calendar", filename="termin.ics",
                       params={"method": "PUBLISH"})
    return msg.as_bytes()


def send(raw: bytes) -> None:
    """Hand the mail to ``himalaya message send`` (stdin)."""
    cmd = [config.himalaya(), "message", "send"]
    try:
        done = subprocess.run(cmd, input=raw, capture_output=True,
                              timeout=config.mail_timeout(), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CalendarError(f"Invitation could not be sent ({cmd[0]}): {exc}") from None
    if done.returncode != 0:
        raise CalendarError(
            f"himalaya failed ({done.returncode}): "
            + done.stderr.decode(errors="replace")[:300]
        )


def create_invite(
    title: str,
    start: str,
    duration_minutes: int = 60,
    all_day: bool = False,
    days: int = 1,
    location: str | None = None,
    description: str | None = None,
) -> dict:
    """Build and mail the invitation; returns what was sent."""
    to = config.invite_to()
    if not to:
        raise CalendarError("Invitations are disabled (CALENDAR_INVITE_TO not set).")
    if not title.strip():
        raise CalendarError("title must not be empty")
    tz = ZoneInfo(config.timezone())
    begin = parse_start(start, all_day, tz)
    if all_day:
        end = begin + timedelta(days=max(days, 1))
        when = begin.strftime("%d.%m.%Y") + (
            f" – {(end - timedelta(days=1)).strftime('%d.%m.%Y')}" if days > 1 else ""
        ) + ", all day"
    else:
        if duration_minutes <= 0:
            raise CalendarError("duration_minutes must be positive")
        end = begin + timedelta(minutes=duration_minutes)
        when = f"{begin:%d.%m.%Y %H:%M}–{end:%H:%M}"
    sender = config.invite_from() or to
    ics = build_invite(title.strip(), begin, end, location=location,
                       description=description)
    send(build_mail(sender, to, title.strip(), when, ics))
    return {"sent": True, "to": to, "title": title.strip(), "when": when,
            "start": begin.isoformat(), "end": end.isoformat()}

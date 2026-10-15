"""Tests for the invitation tool (invite.py)."""
import email
import email.policy
import importlib
import stat

import icalendar
import pytest

from mcp_calendar import invite, server
from mcp_calendar.ics import CalendarError


@pytest.fixture
def mailbox(monkeypatch, tmp_path):
    """A fake himalaya that stores the piped mail; returns a reader for it."""
    fake = tmp_path / "himalaya"
    out = tmp_path / "mail.eml"
    fake.write_text(f'#!/bin/sh\necho "$@" > {tmp_path}/args\ncat > {out}\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CALENDAR_HIMALAYA", str(fake))
    monkeypatch.setenv("CALENDAR_INVITE_TO", "max@example.com")

    def read():
        assert (tmp_path / "args").read_text().strip() == "message send"
        return email.message_from_bytes(out.read_bytes(), policy=email.policy.default)
    return read


def _event(mail):
    parts = [p for p in mail.walk() if p.get_content_type() == "text/calendar"]
    assert len(parts) == 1 and parts[0].get_filename() == "termin.ics"
    assert parts[0].get_param("method") == "PUBLISH"
    cal = icalendar.Calendar.from_ical(parts[0].get_content())
    assert str(cal["method"]) == "PUBLISH"
    return next(c for c in cal.walk("VEVENT"))


def test_timed_invite_is_local_time_with_attendee(mailbox):
    result = invite.create_invite("Zahnarzt", "2026-10-17T14:00", duration_minutes=45,
                                  location="Wels")
    assert result["when"] == "17.10.2026 14:00–14:45" and result["to"] == "max@example.com"
    mail = mailbox()
    assert mail["Subject"] == "Termin: Zahnarzt (17.10.2026 14:00–14:45)"
    ev = _event(mail)
    assert str(ev["summary"]) == "Zahnarzt" and str(ev["location"]) == "Wels"
    start = ev.decoded("dtstart")
    assert start.isoformat() == "2026-10-17T14:00:00+02:00"
    assert str(start.tzinfo) == "Europe/Vienna"
    assert "attendee" not in ev and "organizer" not in ev


def test_all_day_invite_over_several_days(mailbox):
    result = invite.create_invite("Urlaub", "2026-12-28", all_day=True, days=3)
    assert result["when"] == "28.12.2026 – 30.12.2026, all day"
    ev = _event(mailbox())
    assert ev.decoded("dtstart").isoformat() == "2026-12-28"
    assert ev.decoded("dtend").isoformat() == "2026-12-31"


def test_bad_input_and_failing_mail(mailbox, monkeypatch):
    with pytest.raises(CalendarError, match="not ISO 8601"):
        invite.create_invite("X", "Freitag 14 Uhr")
    with pytest.raises(CalendarError, match="must not be empty"):
        invite.create_invite(" ", "2026-10-17T14:00")
    monkeypatch.setenv("CALENDAR_HIMALAYA", "/bin/false")
    with pytest.raises(CalendarError, match="himalaya failed"):
        invite.create_invite("X", "2026-10-17T14:00")
    assert mailbox  # fixture sets the recipient


def test_tool_only_offered_with_recipient(monkeypatch):
    async def names():
        return {t.name for t in await server.mcp.list_tools()}
    import asyncio
    monkeypatch.delenv("CALENDAR_INVITE_TO", raising=False)
    assert "create_event_invite" not in asyncio.run(names())
    monkeypatch.setenv("CALENDAR_INVITE_TO", "max@example.com")
    importlib.reload(server)
    assert "create_event_invite" in asyncio.run(names())
    monkeypatch.delenv("CALENDAR_INVITE_TO")
    importlib.reload(server)

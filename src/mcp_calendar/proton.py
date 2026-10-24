"""Creating events directly through the ``proton-cal`` CLI (optional write path).

Proton Calendar has no CalDAV and no public API, so the only way to write
without a mail round-trip is the external ``proton-cal`` binary. This module
builds its command line and runs it; it is registered as a tool only when
``CALENDAR_PROTON_CAL`` points at the binary (the mail path stays the fallback).

The CLI contract (v0.1.2, verified by hand):

    proton-cal create event SUMMARY --start "YYYY-MM-DD HH:MM" --end "…" --tz Europe/Vienna -o json
    # all-day:  --start "YYYY-MM-DD" --end "YYYY-MM-DD" --all-day   (--end is INCLUSIVE)
    # optional: --calendar NAME --location TEXT --description TEXT --reminder 15m

JSON goes to stdout, messages to stderr. Without a login every command refuses
with ``Error: not logged in`` and exit 1, before it even validates arguments.
"""

from __future__ import annotations


def build_command(
    title: str,
    start: str,
    duration_minutes: int = 60,
    all_day: bool = False,
    days: int = 1,
    location: str | None = None,
    description: str | None = None,
    remind_minutes: int | None = None,
    calendar: str | None = None,
) -> list[str]:
    """The argv of one ``proton-cal create event`` call.

    Order and shape are fixed (the fake binary in the tests pins them):
    ``[proton_cal(), "create", "event", title, "--start", <start>, "--end", <end>,
    "--tz", config.timezone(), "-o", "json"]`` — followed by, in this order and
    only when set: ``"--all-day"``, ``"--calendar", calendar``,
    ``"--location", location``, ``"--description", description``,
    ``"--reminder", f"{remind_minutes}m"``.

    Start format: timed events ``"YYYY-MM-DD HH:MM"``, all-day events
    ``"YYYY-MM-DD"``. ``start`` is accepted in the same ISO 8601 form as the
    invite tool and parsed with :func:`mcp_calendar.invite.parse_start`.

    End: timed events are ``start + duration_minutes``; all-day events are
    ``start + days - 1`` because the CLI treats ``--end`` as **inclusive**
    (``days=3`` from 2026-12-28 therefore ends on 2026-12-30).

    Raises:
        CalendarError: an empty title ("title must not be empty") or an
            unparsable start (the message of ``parse_start``).
    """
    raise NotImplementedError


def create_event(
    title: str,
    start: str,
    duration_minutes: int = 60,
    all_day: bool = False,
    days: int = 1,
    location: str | None = None,
    description: str | None = None,
    remind_minutes: int | None = None,
    calendar: str | None = None,
) -> dict:
    """Run the CLI once and describe what happened.

    ``subprocess.run(build_command(...), capture_output=True,
    timeout=config.proton_timeout(), check=False)``.

    Returns:
        ``{"ok": True, "title": title, "start": <as formatted for the CLI>,
        "end": <as formatted for the CLI>, "timezone": config.timezone(),
        "calendar": calendar, "result": <parsed json or {"raw": stdout}>}``.
        A JSON stdout that does not parse is **not** an error as long as the
        exit code is 0 — then ``result`` is ``{"raw": stdout.strip()}``.

    Raises:
        CalendarError:
            missing binary → ``"proton-cal not found at <path> — set CALENDAR_PROTON_CAL"``;
            timeout → ``"proton-cal timed out after <n>s"``;
            exit code ≠ 0 → ``"proton-cal failed (<code>): <stderr, 300 chars>"``;
            plus the two validation errors from :func:`build_command`, which must
            fire **before** the process is started.
    """
    raise NotImplementedError

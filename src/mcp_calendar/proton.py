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

import json
import subprocess
from datetime import timedelta
from zoneinfo import ZoneInfo

from . import config
from .ics import CalendarError
from .invite import parse_start


def _cli_window(
    start: str, all_day: bool, duration_minutes: int, days: int
) -> tuple[str, str]:
    """The ``--start``/``--end`` strings of the CLI for one event.

    All-day events use bare dates and an **inclusive** end, so ``days=3``
    starting 2026-12-28 ends 2026-12-30.
    """
    tz = ZoneInfo(config.timezone())
    begin = parse_start(start, all_day, tz)
    if all_day:
        end = begin + timedelta(days=days - 1)
        return begin.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    end = begin + timedelta(minutes=duration_minutes)
    return begin.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M")


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
    if not title.strip():
        raise CalendarError("title must not be empty")
    begin, end = _cli_window(start, all_day, duration_minutes, days)
    cmd = [
        config.proton_cal(),
        "create",
        "event",
        title.strip(),
        "--start",
        begin,
        "--end",
        end,
        "--tz",
        config.timezone(),
        "-o",
        "json",
    ]
    if all_day:
        cmd.append("--all-day")
    if calendar:
        cmd += ["--calendar", calendar]
    if location:
        cmd += ["--location", location]
    if description:
        cmd += ["--description", description]
    if remind_minutes is not None:
        cmd += ["--reminder", f"{remind_minutes}m"]
    return cmd


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
    cmd = build_command(
        title,
        start,
        duration_minutes=duration_minutes,
        all_day=all_day,
        days=days,
        location=location,
        description=description,
        remind_minutes=remind_minutes,
        calendar=calendar,
    )
    begin, end = _cli_window(start, all_day, duration_minutes, days)
    try:
        done = subprocess.run(
            cmd, capture_output=True, timeout=config.proton_timeout(), check=False
        )
    except subprocess.TimeoutExpired:
        raise CalendarError(
            f"proton-cal timed out after {config.proton_timeout():g}s"
        ) from None
    except OSError:
        raise CalendarError(
            f"proton-cal not found at {config.proton_cal()} "
            "— set CALENDAR_PROTON_CAL"
        ) from None
    if done.returncode != 0:
        raise CalendarError(
            f"proton-cal failed ({done.returncode}): "
            + done.stderr.decode(errors="replace")[:300]
        )
    stdout = done.stdout.decode(errors="replace")
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = {"raw": stdout.strip()}
    return {
        "ok": True,
        "title": title.strip(),
        "start": begin,
        "end": end,
        "timezone": config.timezone(),
        "calendar": calendar,
        "result": parsed,
    }

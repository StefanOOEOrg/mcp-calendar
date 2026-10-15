"""Runtime configuration, read from the environment on every access.

Multiple calendars are supported via ``CALENDAR_URLS``, a single-line JSON
object mapping a friendly name to its ICS share URL, e.g.::

    CALENDAR_URLS={"My calendar": "https://...", "Work": "https://..."}

For a single calendar, ``CALENDAR_ICS_URL`` alone also works (registered
under the name ``default``).
"""

from __future__ import annotations

import json
import os


def calendars() -> dict[str, str]:
    raw = os.environ.get("CALENDAR_URLS", "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"CALENDAR_URLS is not valid JSON: {exc}") from None
        if not isinstance(data, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()
        ):
            raise ValueError("CALENDAR_URLS must be a JSON object of {name: url}")
        return data
    single = os.environ.get("CALENDAR_ICS_URL", "").strip()
    return {"default": single} if single else {}


def timezone() -> str:
    return os.environ.get("CALENDAR_TIMEZONE", "Europe/Vienna")


def fetch_timeout() -> float:
    return float(os.environ.get("CALENDAR_FETCH_TIMEOUT", "20"))


def invite_to() -> str:
    """Recipient of invitations; empty = the invitation tool is not offered."""
    return os.environ.get("CALENDAR_INVITE_TO", "").strip()


def invite_from() -> str:
    """Sender/organizer of invitations (default: the recipient)."""
    return os.environ.get("CALENDAR_INVITE_FROM", "").strip()


def himalaya() -> str:
    return os.environ.get("CALENDAR_HIMALAYA", "").strip() or "himalaya"


def mail_timeout() -> float:
    return float(os.environ.get("CALENDAR_MAIL_TIMEOUT", "60"))

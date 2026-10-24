"""Shared pytest fixtures for mcp-calendar tests."""
import sys
from pathlib import Path

import pytest

# src-layout: ensure src/ is importable in tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

CALENDAR_ENV = (
    "CALENDAR_URLS",
    "CALENDAR_ICS_URL",
    "CALENDAR_INVITE_TO",
    "CALENDAR_INVITE_FROM",
    "CALENDAR_HIMALAYA",
    "CALENDAR_MAIL_TIMEOUT",
    "CALENDAR_FETCH_TIMEOUT",
)


@pytest.fixture(autouse=True)
def isolated_calendar_env(monkeypatch):
    """Kein Test darf von der Umgebung des Rechners abhängen (Issue #1, WP1).

    Löscht alle CALENDAR_*-Variablen und pinnt die Zeitzone auf Europe/Vienna.
    Ein ``monkeypatch.setenv`` im Test selbst gewinnt weiterhin, weil es nach
    dieser Fixture läuft.
    """
    for name in CALENDAR_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CALENDAR_TIMEZONE", "Europe/Vienna")

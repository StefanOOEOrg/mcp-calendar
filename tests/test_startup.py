"""Startup behaviour of the stdio server (Issue #1, WP1).

Der Server darf ohne Konfiguration nicht abbrechen (ein stdio-Server, der mit
Exit 1 stirbt, gibt dem Client keine Antwort mehr) — aber er darf auch nicht
stumm starten. Der Hinweis gehört auf **stderr**: stdout ist der Protokollkanal.
"""
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def _run_server(**env):
    """Start ``python -m mcp_calendar`` with stdin closed and no CALENDAR_* env."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("CALENDAR_")}
    clean["PYTHONPATH"] = str(SRC)
    clean.update(env)
    return subprocess.run(
        [sys.executable, "-m", "mcp_calendar"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
        env=clean,
        check=False,
    )


def test_start_without_config_warns_on_stderr_and_keeps_running():
    done = _run_server()
    assert done.returncode == 0
    assert done.stdout == b"", "stdout ist der MCP-Protokollkanal und muss leer bleiben"
    assert b"no calendar configured" in done.stderr
    assert b"Traceback" not in done.stderr


def test_start_with_config_is_silent():
    done = _run_server(CALENDAR_ICS_URL="https://example.com/a.ics")
    assert done.returncode == 0
    assert done.stdout == b""
    assert done.stderr == b""


def test_start_with_broken_config_reports_the_reason_without_crashing():
    done = _run_server(CALENDAR_URLS="{not json")
    assert done.returncode == 0
    assert b"Traceback" not in done.stderr
    assert b"not valid JSON" in done.stderr

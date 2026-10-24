"""Tests for the direct write path (proton.py).

The executable is always a fake shell script, so nothing here needs the real
``proton-cal`` or a Proton login.
"""

import stat

import pytest

from mcp_calendar import proton
from mcp_calendar.ics import CalendarError


@pytest.fixture
def fake_cli(monkeypatch, tmp_path):
    """Install a fake ``proton-cal``; returns a function to set up its answer."""

    def install(stdout: str = '{"uid": "abc"}', stderr: str = "", exit_code: int = 0):
        script = tmp_path / "proton-cal"
        script.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$@" > "{tmp_path / "args"}"\n'
            f'cat "{tmp_path / "stdout"}"\n'
            f'cat "{tmp_path / "stderr"}" >&2\n'
            f"exit {exit_code}\n"
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        (tmp_path / "stdout").write_text(stdout)
        (tmp_path / "stderr").write_text(stderr)
        monkeypatch.setenv("CALENDAR_PROTON_CAL", str(script))
        monkeypatch.setenv("CALENDAR_TIMEZONE", "Europe/Vienna")
        return tmp_path / "args"

    return install


def args_of(path) -> list[str]:
    return path.read_text().splitlines()


def test_timed_command_has_the_fixed_shape(fake_cli):
    fake_cli()

    cmd = proton.build_command("Zahnarzt", "2026-10-17T14:00", duration_minutes=45)

    assert cmd[1:5] == ["create", "event", "Zahnarzt", "--start"]
    assert cmd[5] == "2026-10-17 14:00"
    assert cmd[6] == "--end"
    assert cmd[7] == "2026-10-17 14:45"
    assert cmd[8:] == ["--tz", "Europe/Vienna", "-o", "json"]


def test_all_day_command_treats_the_end_as_inclusive(fake_cli):
    fake_cli()

    cmd = proton.build_command("Urlaub", "2026-12-28", all_day=True, days=3)

    assert cmd[5] == "2026-12-28"
    assert cmd[7] == "2026-12-30"  # three days: 28., 29., 30.
    assert "--all-day" in cmd


def test_optional_flags_only_when_set(fake_cli):
    fake_cli()

    plain = proton.build_command("Kaffee", "2026-10-17T09:00")
    assert "--calendar" not in plain
    assert "--reminder" not in plain
    assert "--location" not in plain
    assert "--description" not in plain

    full = proton.build_command(
        "Kaffee",
        "2026-10-17T09:00",
        location="Café Sperl",
        description="mit Anna",
        remind_minutes=15,
        calendar="Privat",
    )
    assert full[full.index("--calendar") + 1] == "Privat"
    assert full[full.index("--location") + 1] == "Café Sperl"
    assert full[full.index("--description") + 1] == "mit Anna"
    assert full[full.index("--reminder") + 1] == "15m"


def test_empty_title_fails_before_the_cli_runs(fake_cli):
    recorded = fake_cli()

    with pytest.raises(CalendarError, match="title must not be empty"):
        proton.create_event("  ", "2026-10-17T14:00")

    assert not recorded.exists()


def test_unparsable_start_is_rejected(fake_cli):
    recorded = fake_cli()

    with pytest.raises(CalendarError, match="is not ISO 8601"):
        proton.create_event("Zahnarzt", "17.10.2026 14:00")

    assert not recorded.exists()


def test_json_stdout_is_parsed_and_described(fake_cli):
    fake_cli(stdout='{"uid": "abc", "calendar": "Privat"}')

    result = proton.create_event("Zahnarzt", "2026-10-17T14:00", duration_minutes=45)

    assert result["ok"] is True
    assert result["title"] == "Zahnarzt"
    assert result["start"] == "2026-10-17 14:00"
    assert result["end"] == "2026-10-17 14:45"
    assert result["timezone"] == "Europe/Vienna"
    assert result["result"] == {"uid": "abc", "calendar": "Privat"}


def test_plain_text_stdout_becomes_raw(fake_cli):
    fake_cli(stdout="Event created successfully")

    result = proton.create_event("Zahnarzt", "2026-10-17T14:00")

    assert result["result"] == {"raw": "Event created successfully"}


def test_nonzero_exit_reports_code_and_stderr(fake_cli):
    fake_cli(stderr="Error: not logged in; run `proton-cal login` first", exit_code=1)

    with pytest.raises(CalendarError) as excinfo:
        proton.create_event("Zahnarzt", "2026-10-17T14:00")

    message = str(excinfo.value)
    assert "proton-cal failed (1)" in message
    assert "not logged in" in message


def test_missing_binary_names_the_configured_path(monkeypatch, tmp_path):
    missing = tmp_path / "gibt-es-nicht"
    monkeypatch.setenv("CALENDAR_PROTON_CAL", str(missing))
    monkeypatch.setenv("CALENDAR_TIMEZONE", "Europe/Vienna")

    with pytest.raises(CalendarError) as excinfo:
        proton.create_event("Zahnarzt", "2026-10-17T14:00")

    assert "not found at" in str(excinfo.value)
    assert str(missing) in str(excinfo.value)


def test_timeout_is_reported(monkeypatch, tmp_path):
    script = tmp_path / "proton-cal-slow"
    script.write_text("#!/bin/sh\nsleep 5\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CALENDAR_PROTON_CAL", str(script))
    monkeypatch.setenv("CALENDAR_PROTON_TIMEOUT", "0.2")
    monkeypatch.setenv("CALENDAR_TIMEZONE", "Europe/Vienna")

    with pytest.raises(CalendarError, match="timed out after"):
        proton.create_event("Zahnarzt", "2026-10-17T14:00")

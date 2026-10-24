"""Tests for the direct write tool (server.create_event)."""

import asyncio
import importlib
import stat

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_calendar import server


def tool_names() -> set[str]:
    """The tool names the server currently offers."""

    async def names():
        return {tool.name for tool in await server.mcp.list_tools()}

    return asyncio.run(names())


@pytest.fixture(name="fake_cli")
def _fake_cli(monkeypatch, tmp_path):
    """A fake proton-cal that records its argv and answers with JSON."""
    binary = tmp_path / "proton-cal"
    argv_file = tmp_path / "argv"
    binary.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" > "{argv_file}"\n'
        'printf \'{"uid": "abc"}\'\n'
    )
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CALENDAR_PROTON_CAL", str(binary))
    monkeypatch.setenv("CALENDAR_TIMEZONE", "Europe/Vienna")
    return argv_file


def test_tool_is_not_offered_without_the_binary(monkeypatch):
    """Without CALENDAR_PROTON_CAL the server keeps its read-only surface."""
    monkeypatch.delenv("CALENDAR_PROTON_CAL", raising=False)
    monkeypatch.delenv("CALENDAR_INVITE_TO", raising=False)
    importlib.reload(server)

    assert "create_event" not in tool_names()

    importlib.reload(server)


def test_tool_is_offered_with_the_binary(monkeypatch, fake_cli):
    """A configured binary adds the direct write tool."""
    monkeypatch.delenv("CALENDAR_INVITE_TO", raising=False)
    importlib.reload(server)

    assert "create_event" in tool_names()

    importlib.reload(server)


def test_both_write_paths_can_be_offered_together(monkeypatch, fake_cli):
    """Direct write and mail invitation coexist; the instructions prefer the direct one."""
    monkeypatch.setenv("CALENDAR_INVITE_TO", "max@example.com")
    importlib.reload(server)

    names = tool_names()

    assert {"create_event", "create_event_invite"} <= names
    assert "Prefer create_event" in server.mcp.instructions

    importlib.reload(server)


def test_arguments_reach_the_cli(fake_cli):
    """remind_minutes and calendar end up in the argv, the result is the CLI answer."""
    result = server.create_event(
        "Zahnarzt",
        "2026-10-17T14:00",
        duration_minutes=45,
        remind_minutes=15,
        calendar="Privat",
    )

    argv = fake_cli.read_text().splitlines()
    assert result["ok"] is True
    assert result["title"] == "Zahnarzt"
    assert result["result"] == {"uid": "abc"}
    assert argv[argv.index("--reminder") + 1] == "15m"
    assert argv[argv.index("--calendar") + 1] == "Privat"
    assert argv[argv.index("--end") + 1] == "2026-10-17 14:45"


def test_line_breaks_in_the_text_fields_are_rejected(fake_cli):
    """A newline would break the invitation and the CLI argument alike."""
    for field in ("title", "location", "description"):
        arguments = {"title": "Zahnarzt", "start": "2026-10-17T14:00", field: "Zeile1\nZeile2"}
        with pytest.raises(ToolError, match="must not contain line breaks"):
            server.create_event(**arguments)


def test_cli_errors_become_tool_errors(monkeypatch, tmp_path):
    """A failing binary surfaces as ToolError, not as a raw exception."""
    binary = tmp_path / "proton-cal-fail"
    binary.write_text("#!/bin/sh\necho 'Error: not logged in' >&2\nexit 1\n")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CALENDAR_PROTON_CAL", str(binary))
    monkeypatch.setenv("CALENDAR_TIMEZONE", "Europe/Vienna")

    with pytest.raises(ToolError, match="not logged in"):
        server.create_event("Zahnarzt", "2026-10-17T14:00")

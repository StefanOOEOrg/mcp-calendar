"""Tests for config.py."""
import pytest

from mcp_calendar import config


def test_calendars_empty_when_unset(monkeypatch):
    monkeypatch.delenv("CALENDAR_URLS", raising=False)
    monkeypatch.delenv("CALENDAR_ICS_URL", raising=False)
    assert config.calendars() == {}


def test_calendars_single_url_backward_compat(monkeypatch):
    monkeypatch.delenv("CALENDAR_URLS", raising=False)
    monkeypatch.setenv("CALENDAR_ICS_URL", "https://example.com/a.ics")
    assert config.calendars() == {"default": "https://example.com/a.ics"}


def test_calendars_multi_json(monkeypatch):
    monkeypatch.setenv(
        "CALENDAR_URLS",
        '{"Work": "https://example.com/w.ics", "Home": "https://example.com/h.ics"}',
    )
    assert config.calendars() == {
        "Work": "https://example.com/w.ics",
        "Home": "https://example.com/h.ics",
    }


def test_calendars_invalid_json_raises(monkeypatch):
    monkeypatch.setenv("CALENDAR_URLS", "{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        config.calendars()


def test_calendars_non_dict_json_raises(monkeypatch):
    monkeypatch.setenv("CALENDAR_URLS", "[1, 2, 3]")
    with pytest.raises(ValueError, match="JSON object"):
        config.calendars()


def test_calendars_non_string_values_raise(monkeypatch):
    monkeypatch.setenv("CALENDAR_URLS", '{"Work": 123}')
    with pytest.raises(ValueError, match="JSON object"):
        config.calendars()


def test_timezone_default(monkeypatch):
    monkeypatch.delenv("CALENDAR_TIMEZONE", raising=False)
    assert config.timezone() == "Europe/Vienna"


def test_timezone_override(monkeypatch):
    monkeypatch.setenv("CALENDAR_TIMEZONE", "America/New_York")
    assert config.timezone() == "America/New_York"


def test_fetch_timeout_default(monkeypatch):
    monkeypatch.delenv("CALENDAR_FETCH_TIMEOUT", raising=False)
    assert config.fetch_timeout() == 20.0

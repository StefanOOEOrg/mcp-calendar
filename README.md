# mcp-calendar

[![CI](https://github.com/StefanOOEOrg/mcp-calendar/actions/workflows/ci.yml/badge.svg)](https://github.com/StefanOOEOrg/mcp-calendar/actions/workflows/ci.yml)

MCP server for on-demand queries against one or more ICS calendar share links
(e.g. Proton Calendar's public "share with anyone" link), plus optional
**invitations by mail** to add appointments.

No direct write access (the share links are read-only), no background
polling — every call fetches fresh.

## Requirements

- **Python 3.10 or newer** (the CI runs 3.10 and 3.14).
- Network access to the ICS share links.
- Only for invitations: the [`himalaya`](https://github.com/pimalaya/himalaya) CLI, configured so
  that it can send mail non-interactively.

## Installation

```bash
git clone https://github.com/StefanOOEOrg/mcp-calendar.git
cd mcp-calendar
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env        # fill in CALENDAR_URLS or CALENDAR_ICS_URL
```

Then start it over stdio (`python -m mcp_calendar`, or the `mcp-calendar` script) and point your
MCP client at it. Nothing listens on a port; the process speaks MCP on stdin/stdout.

## Configuration

All settings come from the environment; a `.env` file in the repo root works too
(copy `.env.example`).

| Variable | Meaning | Default |
|---|---|---|
| `CALENDAR_URLS` | single-line JSON object `{"Name": "ICS share URL", …}` | — |
| `CALENDAR_ICS_URL` | one ICS URL; used only when `CALENDAR_URLS` is unset, registered under the name `default` | — |
| `CALENDAR_TIMEZONE` | IANA zone used for "now" and day boundaries | `Europe/Vienna` |
| `CALENDAR_FETCH_TIMEOUT` | seconds per ICS fetch | `20` |
| `CALENDAR_INVITE_TO` | recipient of invitations; **only with this set** the `create_event_invite` tool is offered | — |
| `CALENDAR_INVITE_FROM` | sender/organizer of the invitation mail | = `CALENDAR_INVITE_TO` |
| `CALENDAR_HIMALAYA` | path of the `himalaya` CLI that sends the mail | `himalaya` |
| `CALENDAR_MAIL_TIMEOUT` | seconds for one mail call | `60` |

`CALENDAR_URLS` example:

```
CALENDAR_URLS={"My calendar": "https://calendar.proton.me/api/calendar/v1/url/…/calendar.ics", "Family": "https://…"}
```

A broken `CALENDAR_URLS` (invalid JSON, wrong shape) is reported as
`CALENDAR_URLS is not valid JSON: …` instead of silently yielding zero calendars.

## Tools

All tools are read-only except the two write paths: `create_event` (direct, optional) and
`create_event_invite` (mail invitation, optional).

- `list_calendars()` — the configured calendar names, sorted.
- `list_events(days_ahead=7, calendar=None)` — events from now through `days_ahead` days out,
  across all calendars or only the one named by `calendar` (see `list_calendars()`). Recurring
  events (RRULE) are expanded via `recurring-ical-events`. Each event carries `calendar`,
  `summary`, `start`, `end` (ISO 8601, local time), `all_day`, `location`, `description`.
- `day_agenda(day=None, language="en")` — one day (default today, `day` as `YYYY-MM-DD`) as
  ready-made briefing lines: all-day events first, then by time with overlaps marked ⚠, calendars
  whose name contains "birthday" as 🎂 lines, calendars starting with "TV" last. `language` is
  `en` or `de`. A `day` that is not `YYYY-MM-DD` is refused with a readable message.
- `create_event_invite(title, start, duration_minutes=60, all_day=False, days=1, location=None,
  description=None)` — mails the event as one `termin.ics` attachment to `CALENDAR_INVITE_TO`.
  `start` is local ISO 8601 (`2026-10-17T14:00`, or `2026-10-17` with `all_day=True`); `days` is
  the length of an all-day event. **Offered only when `CALENDAR_INVITE_TO` is set.** The
  attachment is `text/calendar; method=PUBLISH` (no organizer, no attendees), because Proton
  Mail shows its "Add to Proton Calendar" button for a PUBLISH — a REQUEST from your own address
  to yourself shows no such button. Afterwards the invitation sits in the mailbox and has to be
  accepted there.

- `create_event(title, start, duration_minutes=60, all_day=False, days=1, location=None,
  description=None, remind_minutes=None, calendar=None)` — writes the event **directly** into the
  Proton calendar through the `proton-cal` CLI; no mail, no acceptance step. `remind_minutes` adds a
  single reminder, `calendar` picks a calendar (default: the CLI's own). **Offered only when
  `CALENDAR_PROTON_CAL` points at the binary.** Where both write paths exist, an agent should
  prefer this one.

## Creating events

Proton Calendar has no CalDAV and no public API, so there are two ways to add an event, and both
are optional:

1. **Direct (`create_event`, recommended when available).** Needs the external Go binary
   `proton-cal` binary (Go, Unlicense) in a **pinned** version (v0.1.2, SHA256 checked against the
   release's `checksums.txt`) and a one-time interactive `proton-cal login` **on the
   machine that runs this server** — the session and the derived key passphrase live in
   `~/.config/proton-cal/` (mode 0600); the account password is never stored. Point
   `CALENDAR_PROTON_CAL` at the binary. This path is unofficial: it uses Proton's private API and
   can break with any Proton release, which is why it stays optional and pinned.
2. **Mail invitation (`create_event_invite`, the fallback).** Needs a local `himalaya` CLI and
   `CALENDAR_INVITE_TO`. The event arrives as a `text/calendar` attachment that Proton Mail turns
   into an "Add to Proton Calendar" button.

Neither path can **change or cancel** an existing event — `proton-cal` could, the mail cannot, and
this server deliberately does not offer it. Recurring events can only be read.

## Project structure

```
mcp-calendar/
├── src/mcp_calendar/
│   ├── __init__.py
│   ├── __main__.py          # python -m mcp_calendar
│   ├── config.py            # CALENDAR_* from the environment, read on every access
│   ├── ics.py               # fetching and parsing the share links, RRULE expansion
│   ├── invite.py            # iCalendar (PUBLISH) + mail via himalaya
│   └── server.py            # the MCP tools, tool_errors(), main()
├── tests/
│   ├── conftest.py
│   ├── fixtures/sample.ics
│   ├── test_config.py       # CALENDAR_URLS parsing and defaults
│   ├── test_ics.py          # parsing, recurrence, broken feeds
│   ├── test_invite.py       # invitation content and the mail call
│   ├── test_server.py       # the four tools and their error messages
│   └── test_startup.py      # startup without configuration
├── .github/workflows/ci.yml # pytest + ruff on 3.10 and 3.14
├── .env.example             # copy to .env, fill in the calendar URLs
├── LICENSE
├── pyproject.toml
└── README.md
```

## Development

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests   # lint gate, must stay clean
```

The tests use recorded ICS fixtures and mock the network and the mail call — no calendar account
and no `himalaya` needed.

## Run

```bash
python -m mcp_calendar
```

## Scope / Limitations

- A single-user tool, not a service: it runs locally over stdio — no network port, no
  authentication, no multi-user support.
- Reading goes over the read-only ICS share links; writing only through the two optional paths
  above (direct `proton-cal` or mail invitation). Without either, the server is read-only.
- Proton's CalDAV situation is unchanged: *"Proton Calendar doesn't support CalDAV, so you can't
  set up a direct two-way sync with an external calendar. The only option right now is to subscribe
  to a calendar via a shared link, which gives you read-only access."* — the "right now" is the
  reason the ICS path stays: if CalDAV ever arrives, a standard client replaces the CLI.
- Changing or cancelling an event is not supported by either write path.
- Invitations need a local `himalaya` CLI that can send mail non-interactively; without it the
  other three tools still work.
- No background polling and no cache: every call fetches the feeds fresh, so a slow or unreachable
  feed slows that call down. Keep the call rate low.
- Recurring events are expanded by `recurring-ical-events`; exotic rules or broken feeds surface
  as a readable tool error instead of silently dropping events.
- Calendar data is personal: share links are secrets, keep `.env` out of the repo.

## License

[MIT](LICENSE) — Copyright (c) 2026 StefanOOE.

# mcp-calendar

MCP server for on-demand queries against one or more ICS calendar share links
(e.g. Proton Calendar's public "share with anyone" link), plus optional
**invitations by mail** to add appointments.

No direct write access (the share links are read-only), no background
polling — every call fetches fresh.

## Configuration

`CALENDAR_URLS` — single-line JSON object mapping a friendly calendar name to
its ICS share URL:

```
CALENDAR_URLS={"My calendar": "https://...", "Family": "https://..."}
```

For a single calendar, `CALENDAR_ICS_URL` alone also works.

Optional: `CALENDAR_TIMEZONE` (default `Europe/Vienna`), `CALENDAR_FETCH_TIMEOUT`
(seconds, default `20`).

Invitations (only offered when `CALENDAR_INVITE_TO` is set):
`CALENDAR_INVITE_TO` (recipient), `CALENDAR_INVITE_FROM` (sender/organizer,
default = recipient), `CALENDAR_HIMALAYA` (path of the `himalaya` CLI that sends
the mail, default `himalaya`), `CALENDAR_MAIL_TIMEOUT` (seconds, default `60`).

## Tools

- `list_calendars()` — configured calendar names.
- `list_events(days_ahead=7, calendar=None)` — events from now through
  `days_ahead` days out, across all calendars (or one, via `calendar`).
  Expands recurring events (RRULE) via `recurring-ical-events`.
- `day_agenda(day=None, language="en")` — one day (default today) as ready-made
  briefing lines: all-day events first, then by time with overlaps marked ⚠,
  calendars named like "Birthdays" as 🎂 lines, calendars starting with "TV" last.
  `language` `en` or `de`.
- `create_event_invite(title, start, duration_minutes=60, all_day=False, days=1,
  location=None, description=None)` — mails the event as one `termin.ics`
  attachment (`text/calendar; method=PUBLISH`, no organizer/attendees) to
  `CALENDAR_INVITE_TO`; Proton Mail offers "Add to Proton Calendar" for it (a
  REQUEST from your own address to yourself shows no such button). `start` is
  local ISO 8601.

## Run

```bash
python -m mcp_calendar
```

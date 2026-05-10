"""Quick-add for native Reminders.app and Calendar.app.

Both apps expose AppleScript dictionaries that we drive directly - no
Google account needed. Times are passed as ISO 8601 from Python and
applied component-by-component on the AppleScript side, so locale-specific
date parsing never enters the picture.

Permissions: first invocation triggers a one-time consent dialog from
Reminders / Calendar. Approve it once and the agent runs unattended.
"""

import logging
from datetime import datetime, timedelta

from livekit.agents import RunContext, function_tool

from tools.mac.utils import (
    applescript_quote,
    is_permission_error,
    macos_only,
    run_osascript,
)

logger = logging.getLogger(__name__)


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO 8601 datetime string. Strips trailing Z."""
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


# AppleScript month names - used so we don't depend on locale parsing.
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _applescript_date_block(var: str, dt: datetime) -> str:
    """Emit AppleScript that builds `var` as a date with `dt`'s components.

    Done component-by-component to avoid locale-dependent date string
    parsing - `date "1/2/2026"` is ambiguous (M/D vs D/M) across regions.
    """
    return (
        f'set {var} to current date\n'
        f'set time of {var} to 0\n'
        f'set day of {var} to 1\n'
        f'set year of {var} to {dt.year}\n'
        f'set month of {var} to {_MONTHS[dt.month - 1]}\n'
        f'set day of {var} to {dt.day}\n'
        f'set hours of {var} to {dt.hour}\n'
        f'set minutes of {var} to {dt.minute}\n'
        f'set seconds of {var} to {dt.second}\n'
    )


@function_tool(
    name="add_reminder",
    description=(
        "Add an item to the user's macOS Reminders.app. Use when the "
        "user says 'remind me to X', 'add X to my groceries list', "
        "'put X on my todo'.\n\n"
        "Args:\n"
        "  title: What to remind about, in the user's words.\n"
        "  due_iso: Optional ISO 8601 datetime for the due/alarm time "
        "(e.g. '2026-05-06T17:00:00'). Use the user's local time. Omit "
        "for an undated reminder.\n"
        "  list_name: Optional Reminders list to add to (e.g. "
        "'Groceries'). Omit to use the default list. The list must "
        "exist - this tool does not create new lists.\n\n"
        "First call shows a one-time Reminders permission prompt."
    ),
)
async def add_reminder(
    context: RunContext,
    title: str,
    due_iso: str | None = None,
    list_name: str | None = None,
) -> str:
    if msg := macos_only("Reminders"):
        return msg
    if not title or not title.strip():
        return "Reminder title is empty."

    title_q = applescript_quote(title.strip())
    props = [f'name:"{title_q}"']
    pre_block = ""

    if due_iso:
        dt = _parse_iso(due_iso)
        if dt is None:
            return f"Could not parse due_iso='{due_iso}' (expected ISO 8601)."
        pre_block += _applescript_date_block("dueDate", dt)
        props.append("due date:dueDate")
        props.append("remind me date:dueDate")

    props_str = ", ".join(props)

    if list_name:
        list_q = applescript_quote(list_name.strip())
        target = f'list "{list_q}"'
        not_found = (
            'on error\n'
            '  return "ERR: list not found"\n'
            'end try\n'
        )
        script = (
            f'{pre_block}'
            f'tell application "Reminders"\n'
            f'  try\n'
            f'    set targetList to {target}\n'
            f'  {not_found}'
            f'  tell targetList to make new reminder with properties {{{props_str}}}\n'
            f'  return "OK"\n'
            f'end tell'
        )
    else:
        script = (
            f'{pre_block}'
            f'tell application "Reminders"\n'
            f'  make new reminder with properties {{{props_str}}}\n'
            f'  return "OK"\n'
            f'end tell'
        )

    rc, out, err = await run_osascript(script, timeout=10.0)
    if rc != 0:
        if is_permission_error(err):
            return (
                "Reminders access is denied. Grant it in System Settings "
                "→ Privacy & Security → Reminders."
            )
        return f"Failed to add reminder: {err or 'unknown error'}"
    if out.startswith("ERR: list not found"):
        return f"Reminders list '{list_name}' does not exist."

    when = ""
    if due_iso:
        dt = _parse_iso(due_iso)
        if dt:
            when = f" for {dt.strftime('%a %b %d at %I:%M %p').replace(' 0', ' ')}"
    location = f" in {list_name}" if list_name else ""
    return f"Added reminder '{title}'{location}{when}."


@function_tool(
    name="add_calendar_event",
    description=(
        "Create an event on the user's macOS Calendar.app. Use when the "
        "user says 'block 3 to 4 tomorrow', 'put dinner on my calendar "
        "Friday at 7', 'schedule a meeting with...'.\n\n"
        "Args:\n"
        "  title: Event title.\n"
        "  start_iso: ISO 8601 start datetime in the user's local time "
        "(e.g. '2026-05-06T15:00:00'). Required.\n"
        "  duration_minutes: Length of the event in minutes (default "
        "30). Ignored if `end_iso` is provided.\n"
        "  end_iso: Optional explicit end datetime. Overrides "
        "duration_minutes.\n"
        "  calendar_name: Optional named calendar to add to (must "
        "already exist). Defaults to the first writable calendar.\n"
        "  location: Optional free-form location string.\n"
        "  notes: Optional notes / description.\n\n"
        "Does not invite anyone. First call shows a Calendar "
        "permission prompt."
    ),
)
async def add_calendar_event(
    context: RunContext,
    title: str,
    start_iso: str,
    duration_minutes: int = 30,
    end_iso: str | None = None,
    calendar_name: str | None = None,
    location: str | None = None,
    notes: str | None = None,
) -> str:
    if msg := macos_only("Calendar"):
        return msg
    if not title or not title.strip():
        return "Event title is empty."

    start_dt = _parse_iso(start_iso)
    if start_dt is None:
        return f"Could not parse start_iso='{start_iso}' (expected ISO 8601)."

    if end_iso:
        end_dt = _parse_iso(end_iso)
        if end_dt is None:
            return f"Could not parse end_iso='{end_iso}' (expected ISO 8601)."
    else:
        end_dt = start_dt + timedelta(minutes=max(1, int(duration_minutes)))

    if end_dt <= start_dt:
        return "Event end must be after start."

    title_q = applescript_quote(title.strip())
    props = [
        f'summary:"{title_q}"',
        "start date:startDate",
        "end date:endDate",
    ]
    if location:
        props.append(f'location:"{applescript_quote(location)}"')
    if notes:
        props.append(f'description:"{applescript_quote(notes)}"')

    pre_block = _applescript_date_block(
        "startDate", start_dt
    ) + _applescript_date_block("endDate", end_dt)

    props_str = ", ".join(props)

    if calendar_name:
        cal_q = applescript_quote(calendar_name.strip())
        target = f'calendar "{cal_q}"'
    else:
        # First calendar with writable=true.
        target = (
            "(first calendar whose writable is true)"
        )

    script = (
        f'{pre_block}'
        f'tell application "Calendar"\n'
        f'  try\n'
        f'    tell {target} to make new event with properties {{{props_str}}}\n'
        f'  on error errMsg\n'
        f'    return "ERR:" & errMsg\n'
        f'  end try\n'
        f'  return "OK"\n'
        f'end tell'
    )

    rc, out, err = await run_osascript(script, timeout=15.0)
    if rc != 0:
        if is_permission_error(err):
            return (
                "Calendar access is denied. Grant it in System Settings "
                "→ Privacy & Security → Calendars."
            )
        return f"Failed to create event: {err or 'unknown error'}"
    if out.startswith("ERR:"):
        detail = out[len("ERR:") :].strip()
        return f"Failed to create event: {detail or 'unknown error'}"

    when = start_dt.strftime("%a %b %d at %I:%M %p").replace(" 0", " ")
    cal_label = f" on {calendar_name}" if calendar_name else ""
    return f"Created '{title}' for {when}{cal_label}."


CALENDAR_TOOLS = [add_reminder, add_calendar_event]

"""Mute/unmute the user's mic during a meeting, by voice.

Each meeting app uses its own toggle hotkey:
  - Zoom (process "zoom.us"):                     ⌘⇧A
  - Microsoft Teams:                              ⌘⇧M
  - Google Meet (running inside a Chromium/Safari
    browser tab):                                 ⌘D - only applied
    when the browser is frontmost AND the active
    tab is on meet.google.com.

Routing rules (in order):
  1. If the frontmost app is a known meeting app, target it directly.
  2. If the frontmost app is a browser whose active tab is Meet,
     target the browser with Meet's hotkey.
  3. Otherwise, scan running apps in priority (Zoom → Teams → browser
     w/ Meet tab) and pick the first match.
  4. If nothing matches, return an actionable error.

Background: the macOS HID system delivers global hotkeys to the
frontmost process only, so we briefly activate the meeting app, send
the keystroke, then return. There's a small (~150ms) flicker; not
ideal but reliable.
"""

import logging

from livekit.agents import RunContext, function_tool

from tools.mac.utils import (
    frontmost_process,
    macos_only,
    process_running,
    run_osascript,
)

logger = logging.getLogger(__name__)

# (process_name, key, modifiers) - modifiers are AppleScript key-down names.
_ZOOM = ("zoom.us", "a", ["command down", "shift down"])
_TEAMS = ("Microsoft Teams", "m", ["command down", "shift down"])
_TEAMS_CLASSIC = ("Microsoft Teams classic", "m", ["command down", "shift down"])

# Browsers whose Meet tab takes ⌘D as the toggle.
_BROWSERS = (
    "Google Chrome",
    "Brave Browser",
    "Microsoft Edge",
    "Arc",
    "Safari",
)
_MEET_HOTKEY = ("d", ["command down"])


async def _browser_active_url(browser: str) -> str | None:
    """Return the URL of the active tab in `browser`, or None."""
    if browser == "Safari":
        script = (
            'tell application "Safari"\n'
            "  if (count of windows) is 0 then return \"\"\n"
            "  return URL of current tab of front window\n"
            "end tell"
        )
    else:
        script = (
            f'tell application "{browser}"\n'
            "  if (count of windows) is 0 then return \"\"\n"
            "  return URL of active tab of front window\n"
            "end tell"
        )
    rc, out, _ = await run_osascript(script, timeout=3.0)
    if rc != 0 or not out:
        return None
    return out


def _is_meet(url: str | None) -> bool:
    return bool(url) and "meet.google.com" in url


async def _send_hotkey(
    app_process: str, key: str, modifiers: list[str], pre_activate: bool
) -> tuple[int, str]:
    """Activate (optionally) then send a keystroke to `app_process`."""
    mods_str = "{" + ", ".join(modifiers) + "}"
    activate_block = ""
    if pre_activate:
        # `activate` works on apps; for browsers and most meeting apps the
        # process name matches the application name. Add a small delay so
        # the OS has time to switch focus before the keystroke fires.
        activate_block = (
            f'tell application "{app_process}" to activate\n'
            "delay 0.15\n"
        )
    script = (
        f"{activate_block}"
        f'tell application "System Events" to keystroke "{key}" using {mods_str}'
    )
    rc, _, err = await run_osascript(script, timeout=5.0)
    return rc, err


async def _try_target_frontmost(
    front: str,
) -> tuple[str | None, str | None]:
    """If `front` is itself a meeting target, send and return (label, err)."""
    if front in (_ZOOM[0],):
        rc, err = await _send_hotkey(_ZOOM[0], _ZOOM[1], _ZOOM[2], pre_activate=False)
        return ("Zoom", None) if rc == 0 else (None, err)
    if front in (_TEAMS[0], _TEAMS_CLASSIC[0]):
        spec = _TEAMS if front == _TEAMS[0] else _TEAMS_CLASSIC
        rc, err = await _send_hotkey(spec[0], spec[1], spec[2], pre_activate=False)
        return ("Microsoft Teams", None) if rc == 0 else (None, err)
    if front in _BROWSERS:
        url = await _browser_active_url(front)
        if _is_meet(url):
            key, mods = _MEET_HOTKEY
            rc, err = await _send_hotkey(front, key, mods, pre_activate=False)
            return (f"Google Meet ({front})", None) if rc == 0 else (None, err)
    return None, None


async def _try_target_running() -> tuple[str | None, str | None]:
    """Frontmost wasn't a meeting; scan running apps in priority."""
    if await process_running(_ZOOM[0]):
        rc, err = await _send_hotkey(_ZOOM[0], _ZOOM[1], _ZOOM[2], pre_activate=True)
        return ("Zoom", None) if rc == 0 else (None, err)
    for spec in (_TEAMS, _TEAMS_CLASSIC):
        if await process_running(spec[0]):
            rc, err = await _send_hotkey(spec[0], spec[1], spec[2], pre_activate=True)
            return ("Microsoft Teams", None) if rc == 0 else (None, err)

    # Browser with a Meet tab - only act if it's truly the active tab,
    # to avoid muting the wrong tab.
    for browser in _BROWSERS:
        if not await process_running(browser):
            continue
        url = await _browser_active_url(browser)
        if _is_meet(url):
            key, mods = _MEET_HOTKEY
            rc, err = await _send_hotkey(browser, key, mods, pre_activate=True)
            return (f"Google Meet ({browser})", None) if rc == 0 else (None, err)
    return None, None


@function_tool(
    name="toggle_meeting_mute",
    description=(
        "Toggle the user's microphone in their current video meeting. "
        "Use when the user says 'mute me', 'unmute', 'mute the mic', "
        "'mute meeting', 'turn my mic off / on'.\n\n"
        "Supports Zoom (⌘⇧A), Microsoft Teams (⌘⇧M), and Google Meet "
        "running in a browser tab (⌘D). Picks the meeting in this "
        "order:\n"
        "  1. Whatever is frontmost, if it's a known meeting app or a "
        "browser whose active tab is Meet.\n"
        "  2. The first running meeting app in the priority order: "
        "Zoom → Teams → browser-with-Meet.\n\n"
        "When the meeting app isn't already frontmost, this tool "
        "activates it briefly to deliver the hotkey - there will be a "
        "~150ms focus flicker. Does NOT report whether the mic ended "
        "up muted or unmuted; the call is a toggle, so trust the "
        "user's prior state. Slack huddles and Discord are not "
        "supported."
    ),
)
async def toggle_meeting_mute(context: RunContext) -> str:
    if msg := macos_only("Meeting mute"):
        return msg

    front = await frontmost_process()
    if front:
        label, err = await _try_target_frontmost(front)
        if label:
            return f"Toggled mic in {label}."
        if err:
            return f"Failed to toggle mic: {err}"

    label, err = await _try_target_running()
    if label:
        return f"Toggled mic in {label}."
    if err:
        return f"Failed to toggle mic: {err}"

    return (
        "No supported meeting found running. Open Zoom, Teams, or a "
        "Google Meet tab and try again."
    )


MEETINGS_TOOLS = [toggle_meeting_mute]

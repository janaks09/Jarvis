"""Toggle macOS Focus modes (Do Not Disturb, Work, Personal, etc.).

macOS does not expose a stable CLI for Focus, so this tool delegates
to a one-time user-created shortcut named exactly **"Set Focus"** in
Shortcuts.app. The shortcut should accept text input and pass it to
the system "Set Focus" action.

One-time setup (60 seconds, asked once):
  1. Open Shortcuts.app and create a new shortcut named "Set Focus".
  2. Add the **Set Focus** action.
  3. Set the focus parameter to "Shortcut Input".
  4. Optionally add a duration parameter.

After that, this tool can flip between any Focus mode the user has
configured in System Settings → Focus.
"""

import logging

from livekit.agents import RunContext, function_tool

from tools.mac.utils import macos_only, run_command

logger = logging.getLogger(__name__)

_SHORTCUT_NAME = "Set Focus"
_SETUP_HINT = (
    "Focus control needs a one-time setup. In Shortcuts.app, create a "
    "shortcut named 'Set Focus' that uses the 'Set Focus' action with "
    "its input wired to 'Shortcut Input'. Then ask again."
)


async def _shortcut_exists() -> bool:
    rc, out, _ = await run_command("shortcuts", "list", timeout=5.0)
    if rc != 0:
        return False
    return any(
        line.strip().lower() == _SHORTCUT_NAME.lower()
        for line in out.splitlines()
    )


@function_tool(
    name="set_focus",
    description=(
        "Turn on a macOS Focus mode (Do Not Disturb, Work, Personal, "
        "Sleep, or any custom Focus the user has set up in System "
        "Settings → Focus). Use when the user says 'turn on do not "
        "disturb', 'start deep work', 'focus mode on', 'silence "
        "notifications'.\n\n"
        "Args:\n"
        "  mode: The Focus name as the user spelled it in System "
        "Settings - 'Do Not Disturb', 'Work', 'Personal', 'Sleep', or "
        "a custom name. Case-insensitive on the macOS side.\n\n"
        "Requires a one-time 'Set Focus' shortcut in Shortcuts.app - "
        "this tool returns clear setup instructions if missing. To "
        "turn focus OFF, call `end_focus`."
    ),
)
async def set_focus(context: RunContext, mode: str) -> str:
    if msg := macos_only("Focus"):
        return msg
    if not mode or not mode.strip():
        return "No focus mode provided."

    if not await _shortcut_exists():
        return _SETUP_HINT

    rc, _, err = await run_command(
        "shortcuts",
        "run",
        _SHORTCUT_NAME,
        stdin=mode.strip().encode("utf-8"),
        timeout=15.0,
    )
    if rc != 0:
        return f"Failed to set focus: {err or 'unknown error'}"
    return f"Focus set to {mode.strip()}."


@function_tool(
    name="end_focus",
    description=(
        "Turn off any active macOS Focus mode. Use when the user says "
        "'turn off do not disturb', 'end focus', 'stop deep work', "
        "'I'm done focusing'.\n\n"
        "Requires the same one-time 'Set Focus' shortcut as `set_focus`."
    ),
)
async def end_focus(context: RunContext) -> str:
    if msg := macos_only("Focus"):
        return msg

    if not await _shortcut_exists():
        return _SETUP_HINT

    # The Set Focus action interprets empty input as "turn off all focuses".
    rc, _, err = await run_command(
        "shortcuts",
        "run",
        _SHORTCUT_NAME,
        stdin=b"",
        timeout=15.0,
    )
    if rc != 0:
        return f"Failed to end focus: {err or 'unknown error'}"
    return "Focus ended."


FOCUS_TOOLS = [set_focus, end_focus]

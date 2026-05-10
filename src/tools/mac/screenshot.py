"""Screen capture for macOS.

Uses the built-in `screencapture` CLI to grab a screenshot and save it
to disk.

Permissions: macOS requires the host process to have **Screen
Recording** permission (System Settings -> Privacy & Security ->
Screen Recording). Without it, `screencapture` returns a blank image.
"""

import logging
import os
import time
from typing import Literal

from livekit.agents import RunContext, function_tool

from tools.mac.utils import macos_only, run_command

logger = logging.getLogger(__name__)


async def _capture(mode: str, dest_path: str) -> tuple[int, str]:
    """Run `screencapture` in the requested mode. Returns (rc, stderr).

    -x silences the camera shutter sound; -i opens the crosshair selector.
    """
    if mode == "screen":
        flags = ["-x"]
    elif mode == "selection":
        flags = ["-x", "-i"]
    else:
        return 2, f"unknown mode: {mode}"

    rc, _, err = await run_command("screencapture", *flags, dest_path, timeout=60.0)
    return rc, err


@function_tool(
    name="screenshot_save",
    description=(
        "Take a screenshot of the user's Mac and save it to disk. Use "
        "when the user says 'take a screenshot', 'save a screenshot', "
        "or 'capture my screen'.\n\n"
        "`mode` selects what to capture:\n"
        "  - 'screen' (default): the entire display(s)\n"
        "  - 'selection': opens the macOS crosshair so the user picks a "
        "region with the mouse - only use when the user explicitly asks "
        "to select an area, since it requires user input.\n\n"
        "Saves to ~/Desktop with a timestamped filename and returns the "
        "path."
    ),
)
async def screenshot_save(
    context: RunContext,
    mode: Literal["screen", "selection"] = "screen",
) -> str:
    if msg := macos_only("Screenshot capture"):
        return msg

    desktop = os.path.expanduser("~/Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.expanduser("~")
    fname = f"Screenshot {time.strftime('%Y-%m-%d at %H.%M.%S')}.png"
    path = os.path.join(desktop, fname)

    rc, err = await _capture(mode, path)
    if rc != 0:
        return f"Failed to capture screen: {err or 'unknown error'}"
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        # User cancelled selection, or permission missing.
        if mode == "selection":
            return "Screenshot cancelled."
        return (
            "Screenshot file was empty - Screen Recording permission may "
            "be missing. Grant it in System Settings -> Privacy & Security "
            "-> Screen Recording."
        )
    return f"Saved screenshot to {path}."


SCREENSHOT_TOOLS = [screenshot_save]

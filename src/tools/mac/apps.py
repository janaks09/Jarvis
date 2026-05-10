"""macOS app launcher and control tools."""

import asyncio
import logging
import sys

from livekit.agents import function_tool, RunContext

logger = logging.getLogger(__name__)

# Allowlist of apps the assistant is permitted to open. Keys are
# lowercase aliases the user might say; values are the canonical
# macOS application names passed to `open -a`.
ALLOWED_APPS: dict[str, str] = {
    "spotify": "Spotify",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "safari": "Safari",
    "slack": "Slack",
    "vscode": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "notes": "Notes",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "finder": "Finder",
    "messages": "Messages",
    "mail": "Mail",
    "calendar": "Calendar",
    "music": "Music",
    "zoom": "zoom.us",
}


@function_tool(
    name="open_mac_app",
    description="""Open a macOS application by name on the user's Mac.

Use this when the user asks to "open", "launch", "start", or "fire up" a Mac app
(e.g. "open Spotify", "launch Chrome", "start VS Code").

Pass the spoken app name in `app_name` (e.g. "spotify", "chrome", "vscode").
Only a fixed allowlist of apps is supported; other names will be rejected.""",
)
async def open_mac_app(context: RunContext, app_name: str) -> str:
    """Open a macOS application by friendly name."""
    if sys.platform != "darwin":
        return "Opening Mac apps is only supported on macOS."

    key = app_name.strip().lower()
    canonical = ALLOWED_APPS.get(key)
    if canonical is None:
        allowed = ", ".join(sorted(set(ALLOWED_APPS.values())))
        return (
            f"App '{app_name}' is not in the allowlist. "
            f"Allowed apps: {allowed}."
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            "open",
            "-a",
            canonical,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
    except FileNotFoundError:
        return "The `open` command is not available on this system."
    except Exception as e:  # noqa: BLE001
        logger.exception("Failed to launch app %s", canonical)
        return f"Failed to open {canonical}: {e}"

    if proc.returncode != 0:
        msg = err.decode(errors="replace").strip() or "unknown error"
        logger.warning("`open -a %s` failed: %s", canonical, msg)
        return f"Failed to open {canonical}: {msg}"

    logger.info("Opened Mac app: %s", canonical)
    return f"Opened {canonical}."

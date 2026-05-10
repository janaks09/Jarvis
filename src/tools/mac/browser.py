"""Active-tab actions for Chrome and Safari on macOS.

Reads the frontmost browser's current tab via AppleScript and can open
a URL in the default browser, Chrome, or Safari (with optional
incognito/private).

Browser selection:
  - If a browser is the frontmost app, that one is used.
  - Otherwise Chrome takes precedence if running, then Safari.
  - If neither is running, the relevant tools return an error.
"""

import logging
import re

from livekit.agents import RunContext, function_tool

from tools.mac.utils import (
    frontmost_process,
    macos_only,
    process_running,
    run_command,
    run_osascript,
)

logger = logging.getLogger(__name__)


async def _pick_browser() -> str | None:
    """Return 'Google Chrome', 'Safari', or None if no browser is usable."""
    front = await frontmost_process()
    if front in ("Google Chrome", "Safari"):
        return front
    if await process_running("Google Chrome"):
        return "Google Chrome"
    if await process_running("Safari"):
        return "Safari"
    return None


async def _active_tab(browser: str) -> tuple[str | None, str | None, str]:
    """Return (url, title, error_or_empty) for the frontmost tab."""
    if browser == "Google Chrome":
        script = (
            'tell application "Google Chrome"\n'
            "  if (count of windows) is 0 then return \"ERR:no windows\"\n"
            "  set t to active tab of front window\n"
            '  return (URL of t) & "\\n" & (title of t)\n'
            "end tell"
        )
    elif browser == "Safari":
        script = (
            'tell application "Safari"\n'
            "  if (count of documents) is 0 then return \"ERR:no documents\"\n"
            "  set d to front document\n"
            '  return (URL of d) & "\\n" & (name of d)\n'
            "end tell"
        )
    else:
        return None, None, f"Unsupported browser: {browser}"

    rc, out, err = await run_osascript(script, timeout=5.0)
    if rc != 0:
        return None, None, err or "AppleScript failed"
    if out.startswith("ERR:"):
        return None, None, out[len("ERR:") :].strip()
    parts = out.split("\n", 1)
    url = parts[0].strip() if parts else ""
    title = parts[1].strip() if len(parts) > 1 else ""
    return url or None, title or None, ""


@function_tool(
    name="browser_active_tab",
    description=(
        "Get the URL and title of the user's currently focused browser "
        "tab on macOS (Chrome or Safari). Use when the user asks "
        "'what tab am I on?', 'what's this page?', or before another "
        "action that needs the URL (sharing, bookmarking).\n\n"
        "Auto-detects which browser is in use. Returns 'Tab: <title> "
        "<url>'. Errors if neither Chrome nor Safari is running."
    ),
)
async def browser_active_tab(context: RunContext) -> str:
    if msg := macos_only("Browser tab access"):
        return msg
    browser = await _pick_browser()
    if browser is None:
        return "Neither Chrome nor Safari is running."
    url, title, err = await _active_tab(browser)
    if err:
        return f"Could not read {browser}'s active tab: {err}"
    return f'Tab in {browser}: "{title}" - {url}'


@function_tool(
    name="browser_open_url",
    description=(
        "Open a URL in a macOS browser. Use when the user says 'open "
        "github dot com', 'pull up the docs', 'open this in a private "
        "window', 'search Google for X'.\n\n"
        "Args:\n"
        "  url: Full URL (with or without https://). Bare strings like "
        "'github.com' are auto-prefixed with https://. For search "
        "queries, the caller should construct the full URL "
        "(https://www.google.com/search?q=...).\n"
        "  browser: 'default' (default), 'chrome', or 'safari'. Use "
        "'default' unless the user names one explicitly.\n"
        "  private: If true, opens in incognito (Chrome) / private "
        "(Safari). Chrome support is robust; Safari requires "
        "Accessibility permission to drive the menu."
    ),
)
async def browser_open_url(
    context: RunContext,
    url: str,
    browser: str = "default",
    private: bool = False,
) -> str:
    if msg := macos_only("Browser open"):
        return msg
    if not url or not url.strip():
        return "No URL provided."

    target = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
        target = "https://" + target

    if private:
        if browser in ("default", "chrome"):
            rc, _, err = await run_command(
                "open",
                "-na",
                "Google Chrome",
                "--args",
                "--incognito",
                target,
                timeout=5.0,
            )
            if rc != 0:
                return f"Failed to open in Chrome incognito: {err}"
            return f"Opened {target} in Chrome incognito."
        if browser == "safari":
            return (
                "Opening directly in Safari Private requires UI scripting "
                "and isn't supported by this tool - use Chrome incognito "
                "instead, or open Safari and switch to Private Browsing "
                "manually."
            )

    if browser == "chrome":
        rc, _, err = await run_command(
            "open", "-a", "Google Chrome", target, timeout=5.0
        )
    elif browser == "safari":
        rc, _, err = await run_command(
            "open", "-a", "Safari", target, timeout=5.0
        )
    else:
        rc, _, err = await run_command("open", target, timeout=5.0)

    if rc != 0:
        return f"Failed to open {target}: {err or 'unknown error'}"
    return f"Opened {target}."


BROWSER_TOOLS = [
    browser_active_tab,
    browser_open_url,
]

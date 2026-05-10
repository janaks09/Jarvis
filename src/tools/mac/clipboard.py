"""Clipboard read / write for macOS.

Bridges `pbpaste`/`pbcopy` so the user can:
  - Hear what's on their clipboard ("what did I just copy?")
  - Drop arbitrary text the agent has produced into the clipboard for
    pasting later.

No app-specific permissions required.
"""

import logging

from livekit.agents import RunContext, function_tool

from tools.mac.utils import macos_only, run_command

logger = logging.getLogger(__name__)


async def _read_clipboard() -> tuple[bool, str]:
    """Return (ok, text). On failure, text is the error message."""
    rc, out, err = await run_command("pbpaste", timeout=5.0)
    if rc != 0:
        return False, err or "pbpaste failed"
    return True, out


async def _write_clipboard(text: str) -> tuple[bool, str]:
    """Set the clipboard to `text`. Returns (ok, error_or_empty)."""
    rc, _, err = await run_command(
        "pbcopy", stdin=text.encode("utf-8"), timeout=5.0
    )
    if rc != 0:
        return False, err or "pbcopy failed"
    return True, ""


def _summarize_for_voice(text: str, limit: int = 800) -> str:
    """Trim a long clipboard payload for the spoken response."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ... (truncated)"


@function_tool(
    name="read_clipboard",
    description=(
        "Read the current text contents of the user's macOS clipboard "
        "and return it. Use when the user says 'what's on my "
        "clipboard?', 'what did I just copy?', or 'read me what I "
        "copied'.\n\n"
        "Returns the clipboard as text (truncated for very long "
        "payloads when speaking aloud). Non-text clipboard content "
        "(images, files) is not supported and will return empty."
    ),
)
async def read_clipboard(context: RunContext) -> str:
    if msg := macos_only("Clipboard"):
        return msg
    ok, content = await _read_clipboard()
    if not ok:
        return f"Couldn't read clipboard: {content}"
    if not content:
        return "Clipboard is empty (or contains non-text content)."
    return _summarize_for_voice(content)


@function_tool(
    name="write_clipboard",
    description=(
        "Replace the user's macOS clipboard with the provided text. Use "
        "when the user says 'copy this to my clipboard', 'put X on the "
        "clipboard', or after composing something on their behalf that "
        "they want to paste elsewhere (e.g. 'draft a reply and copy "
        "it').\n\n"
        "Overwrites whatever was on the clipboard before, without "
        "warning. The text is set verbatim - do not add quotes or "
        "framing the user didn't ask for."
    ),
)
async def write_clipboard(context: RunContext, text: str) -> str:
    if msg := macos_only("Clipboard"):
        return msg
    if text is None:
        return "No text provided."
    ok, err = await _write_clipboard(text)
    if not ok:
        return f"Couldn't write clipboard: {err}"
    char_count = len(text)
    return f"Copied {char_count} characters to the clipboard."


CLIPBOARD_TOOLS = [read_clipboard, write_clipboard]

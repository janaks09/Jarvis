"""macOS Shortcuts.app bridge.

Lets the voice agent run any shortcut from the user's Shortcuts library
by name, with zero per-shortcut configuration. The user builds a
shortcut visually in Shortcuts.app; the agent discovers it
automatically and can invoke it on request.

The bridge is the built-in `shortcuts` CLI (Monterey+). Shortcut names
are loaded once at session start (primed via `prime_shortcut_cache`)
and cached for 5 minutes; the agent can ask for a fresh list at any
time via `list_shortcuts(refresh=true)`.

Resolution rules for `run_shortcut(name=...)`:
  1. Case-insensitive exact match against the live library.
  2. Single case-insensitive substring match (handles voice transcripts
     that drop a word, e.g. "summarize tab" → "Summarize Current Tab").
  3. Otherwise the tool returns the closest suggestions and exits
     without running anything.
"""

import asyncio
import contextlib
import difflib
import logging
import os
import tempfile
import time

from livekit.agents import RunContext, function_tool

from tools.mac.utils import is_macos, macos_only, run_command

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300.0
_RUN_TIMEOUT_SECONDS = 120.0
_LIST_TIMEOUT_SECONDS = 10.0

_cache_lock = asyncio.Lock()
_cache: list[str] | None = None
_cache_at: float = 0.0


async def _fetch_shortcut_names() -> list[str]:
    """Read the user's Shortcuts library via the `shortcuts` CLI."""
    rc, out, err = await run_command(
        "shortcuts", "list", timeout=_LIST_TIMEOUT_SECONDS
    )
    if rc != 0:
        logger.warning("`shortcuts list` failed (rc=%s): %s", rc, err)
        return []
    seen: set[str] = set()
    unique: list[str] = []
    for line in out.splitlines():
        name = line.strip()
        if name and name not in seen:
            seen.add(name)
            unique.append(name)
    return sorted(unique, key=str.lower)


async def _get_shortcut_names(force: bool = False) -> list[str]:
    """Return cached shortcut names, refreshing when stale or forced."""
    global _cache, _cache_at
    async with _cache_lock:
        now = time.time()
        if force or _cache is None or (now - _cache_at) > _CACHE_TTL_SECONDS:
            _cache = await _fetch_shortcut_names()
            _cache_at = now
        return list(_cache)


async def prime_shortcut_cache() -> int:
    """Warm the cache so the first voice invocation is instant.

    Safe to call on non-macOS or when Shortcuts.app is unavailable;
    returns the number of shortcuts discovered (0 on either failure).
    """
    if not is_macos():
        return 0
    try:
        names = await _get_shortcut_names(force=True)
    except Exception:
        logger.exception("Failed to prime Shortcuts cache")
        return 0
    logger.info("Primed Shortcuts cache: %d shortcut(s) available", len(names))
    return len(names)


def _resolve_name(query: str, names: list[str]) -> tuple[str | None, list[str]]:
    """Resolve `query` to an exact shortcut name from `names`.

    Returns (resolved_name_or_None, suggestions). Suggestions are only
    populated when no resolution was possible.
    """
    q = query.strip()
    if not q:
        return None, []

    lower_to_real = {n.lower(): n for n in names}
    if q.lower() in lower_to_real:
        return lower_to_real[q.lower()], []

    contains = [n for n in names if q.lower() in n.lower()]
    if len(contains) == 1:
        return contains[0], []

    if contains:
        return None, contains[:3]
    return None, difflib.get_close_matches(q, names, n=3, cutoff=0.5)


@function_tool(
    name="list_shortcuts",
    description=(
        "List the names of every shortcut in the user's macOS "
        "Shortcuts.app library. Call this when you need to discover "
        "what's available before invoking `run_shortcut`, or when the "
        "user asks 'what shortcuts can I run?'.\n\n"
        "Names are loaded once per session and cached for 5 minutes. "
        "Pass `refresh=true` to force a re-read - only do this if the "
        "user just told you they created or renamed a shortcut.\n\n"
        "Returns a newline-separated list."
    ),
)
async def list_shortcuts(context: RunContext, refresh: bool = False) -> str:
    if msg := macos_only("Shortcuts.app"):
        return msg
    names = await _get_shortcut_names(force=refresh)
    if not names:
        return (
            "No shortcuts found. The user can build one visually in "
            "Shortcuts.app, then ask again (or call this with "
            "refresh=true)."
        )
    return "Available shortcuts:\n" + "\n".join(f"- {n}" for n in names)


@function_tool(
    name="run_shortcut",
    description=(
        "Run a shortcut from the user's macOS Shortcuts.app library by "
        "name and return its text output. Use when a user request maps "
        "to one of their saved shortcuts - e.g. 'summarize this tab', "
        "'add milk to groceries', 'turn on deep work mode', 'what's my "
        "next meeting?', 'find my phone'.\n\n"
        "If you don't know what shortcuts the user has, call "
        "`list_shortcuts` first; do not guess names.\n\n"
        "Args:\n"
        "  name: The shortcut name. Resolved case-insensitively, with "
        "single-substring fallback (so 'summarize tab' will match a "
        "shortcut called 'Summarize Current Tab' if it's the only "
        "match). Ambiguous or missing names return suggestions and do "
        "NOT run anything.\n"
        "  text_input: Optional text passed to the shortcut as input - "
        "use this for shortcuts that accept a URL, query, or prompt. "
        "Omit if the shortcut needs no input.\n\n"
        "Returns the shortcut's text output, or a 'Ran X' confirmation "
        "if it produced no text. Times out after 2 minutes - keep "
        "voice-triggered shortcuts fast."
    ),
)
async def run_shortcut(
    context: RunContext,
    name: str,
    text_input: str | None = None,
) -> str:
    if msg := macos_only("Shortcuts.app"):
        return msg
    if not name or not name.strip():
        return "No shortcut name provided."

    names = await _get_shortcut_names()
    if not names:
        return (
            "The Shortcuts.app library is empty or the `shortcuts` CLI "
            "is unavailable. Create a shortcut in Shortcuts.app first."
        )

    resolved, suggestions = _resolve_name(name, names)
    if resolved is None:
        if suggestions:
            joined = ", ".join(f"'{s}'" for s in suggestions)
            return f"No shortcut named '{name}'. Did you mean: {joined}?"
        return (
            f"No shortcut named '{name}' and no close matches in the "
            f"library. The user has {len(names)} shortcut(s); call "
            f"`list_shortcuts` to see them."
        )

    with tempfile.NamedTemporaryFile(
        suffix=".txt", prefix="jarvis-shortcut-", delete=False
    ) as f:
        out_path = f.name

    try:
        stdin_bytes = text_input.encode("utf-8") if text_input else None
        rc, _, err = await run_command(
            "shortcuts",
            "run",
            resolved,
            "-o",
            out_path,
            stdin=stdin_bytes,
            timeout=_RUN_TIMEOUT_SECONDS,
        )
        if rc != 0:
            return f"Shortcut '{resolved}' failed: {err or 'unknown error'}"
        try:
            with open(out_path, encoding="utf-8", errors="replace") as f:
                output = f.read().strip()
        except OSError as e:
            return f"Ran '{resolved}' but could not read output: {e}"
    finally:
        with contextlib.suppress(OSError):
            os.unlink(out_path)

    return output if output else f"Ran '{resolved}'."


SHORTCUTS_TOOLS = [list_shortcuts, run_shortcut]

"""Shared helpers for macOS tools.

Centralizes the `osascript` invocation and platform-guard pattern used by
the Mac control tools (window, media, messages, screenshot, shell).
"""

import asyncio
import sys


def is_macos() -> bool:
    return sys.platform == "darwin"


def macos_only(feature: str) -> str | None:
    """Return an error string if not on macOS, else None."""
    if not is_macos():
        return f"{feature} is only supported on macOS."
    return None


async def run_osascript(
    script: str,
    *,
    language: str = "AppleScript",
    timeout: float = 10.0,
) -> tuple[int, str, str]:
    """Run an AppleScript (or JXA) snippet via `osascript`.

    Args:
        script: The script source.
        language: "AppleScript" (default) or "JavaScript" for JXA.
        timeout: Hard timeout in seconds; the process is killed if exceeded.

    Returns:
        Tuple of (returncode, stdout, stderr), both decoded and stripped.
        On timeout, returncode is 124 and stderr contains a timeout message.
    """
    args = ["osascript"]
    if language.lower() in ("javascript", "jxa", "js"):
        args += ["-l", "JavaScript"]
    args += ["-e", script]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"osascript timed out after {timeout}s"

    return (
        proc.returncode if proc.returncode is not None else -1,
        out.decode(errors="replace").strip(),
        err.decode(errors="replace").strip(),
    )


def applescript_quote(s: str) -> str:
    """Escape a Python string for embedding in an AppleScript string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


async def frontmost_process() -> str | None:
    """Return the name of the frontmost macOS process, or None on failure."""
    rc, out, _ = await run_osascript(
        'tell application "System Events" to '
        "name of first application process whose frontmost is true",
        timeout=3.0,
    )
    if rc != 0:
        return None
    return out.strip() or None


async def process_running(name: str) -> bool:
    """Return True if a macOS process with `name` is currently running."""
    q = applescript_quote(name)
    rc, out, _ = await run_osascript(
        f'tell application "System Events" to (exists (process "{q}"))',
        timeout=3.0,
    )
    return rc == 0 and out.strip().lower() == "true"


def is_permission_error(err: str) -> bool:
    """Detect macOS TCC / AppleScript permission-denied errors."""
    if not err:
        return False
    return "not authorized" in err.lower() or "1743" in err


async def run_command(
    *args: str,
    timeout: float = 30.0,
    stdin: bytes | None = None,
) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr).

    Used for non-AppleScript tools like `screencapture`, `pbcopy`, etc.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if stdin is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"command timed out after {timeout}s"

    return (
        proc.returncode if proc.returncode is not None else -1,
        out.decode(errors="replace").strip(),
        err.decode(errors="replace").strip(),
    )

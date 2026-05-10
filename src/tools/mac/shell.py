"""Run shell commands in a visible Terminal / iTerm window.

This is *not* a silent shell exec - the command is dispatched to the
user's terminal app so the user can see output, intervene, or reuse the
session. For headless capture of small read-only commands, this tool is
the wrong fit.

Safety: this is arbitrary shell execution. The voice agent should
confirm destructive commands (rm, sudo, force pushes, package
installs) with the user before calling this tool.
"""

import logging
import os
from typing import Literal

from livekit.agents import RunContext, function_tool

from tools.mac.utils import applescript_quote, macos_only, run_osascript

logger = logging.getLogger(__name__)


def _shell_quote(s: str) -> str:
    """POSIX-quote a path for safe inclusion in a shell command."""
    return "'" + s.replace("'", "'\\''") + "'"


def _build_command(cwd: str | None, command: str) -> str:
    """Compose the shell command, prepending `cd` if cwd is provided."""
    cmd = command.strip()
    if cwd:
        expanded = os.path.expanduser(cwd)
        return f"cd {_shell_quote(expanded)} && {cmd}"
    return cmd


async def _run_in_terminal(full_cmd: str) -> tuple[int, str]:
    q = applescript_quote(full_cmd)
    script = f'''
tell application "Terminal"
    activate
    do script "{q}"
end tell
'''
    rc, _, err = await run_osascript(script, timeout=10.0)
    return rc, err


async def _run_in_iterm(full_cmd: str) -> tuple[int, str]:
    q = applescript_quote(full_cmd)
    script = f'''
tell application "iTerm"
    activate
    if (count of windows) is 0 then
        create window with default profile
    else
        tell current window to create tab with default profile
    end if
    tell current session of current window to write text "{q}"
end tell
'''
    rc, _, err = await run_osascript(script, timeout=10.0)
    return rc, err


@function_tool(
    name="run_in_terminal",
    description=(
        "Open a Terminal (or iTerm) window on the user's Mac and run a "
        "shell command in it. The command runs in a *visible* terminal "
        "tab so the user can see output and continue the session - this "
        "is for kicking off dev workflows like `npm run dev`, `git "
        "status`, `pytest`, opening a project, etc.\n\n"
        "Args:\n"
        "  command: The shell command to run, exactly as it should be "
        "typed at a prompt. Do not wrap in extra quotes.\n"
        "  cwd: Optional working directory. Tilde (~) is expanded. If "
        "set, the tool prepends `cd <cwd> &&` to the command.\n"
        "  app: 'terminal' (default) or 'iterm'. Use 'iterm' only when "
        "the user explicitly prefers iTerm.\n\n"
        "DO NOT use this for read-only queries you can answer another "
        "way (e.g. don't run `date` or `pwd` here). DO NOT run "
        "destructive commands (rm -rf, sudo, force push, package "
        "uninstalls) without first confirming with the user out loud. "
        "Returns immediately after dispatching - does not capture "
        "command output."
    ),
)
async def run_in_terminal(
    context: RunContext,
    command: str,
    cwd: str | None = None,
    app: Literal["terminal", "iterm"] = "terminal",
) -> str:
    if msg := macos_only("Terminal dispatch"):
        return msg

    if not command or not command.strip():
        return "No command provided."

    full_cmd = _build_command(cwd, command)

    if app == "iterm":
        rc, err = await _run_in_iterm(full_cmd)
        app_label = "iTerm"
    else:
        rc, err = await _run_in_terminal(full_cmd)
        app_label = "Terminal"

    if rc != 0:
        logger.warning("run_in_terminal failed: %s", err)
        return f"Failed to dispatch to {app_label}: {err or 'unknown error'}"

    where = f" (in {cwd})" if cwd else ""
    return f"Running in {app_label}{where}: {command}"


SHELL_TOOLS = [run_in_terminal]

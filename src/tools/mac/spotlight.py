"""Spotlight-backed file finder + opener for macOS.

Uses `mdfind` (the CLI for the Spotlight index) to locate files,
folders, and apps by name or content, then `open` to surface them.

Two tools:
  - `find_files`: search and return paths (no opening).
  - `open_path`: open a file, folder, app, or URL in the right handler.

Spotlight searches everything that has been indexed; certain folders
(e.g. ~/Library, system caches) are excluded by default.
"""

import logging
import os
from typing import Literal

from livekit.agents import RunContext, function_tool

from tools.mac.utils import macos_only, run_command

logger = logging.getLogger(__name__)

_KIND_MAP: dict[str, str] = {
    "any": "",
    "folder": "kind:folder",
    "app": "kind:application",
    "pdf": "kind:pdf",
    "image": "kind:image",
    "document": "kind:document",
    "music": "kind:music",
    "movie": "kind:movie",
}

Kind = Literal[
    "any", "folder", "app", "pdf", "image", "document", "music", "movie"
]

_DEFAULT_LIMIT = 5
_MAX_LIMIT = 20


@function_tool(
    name="find_files",
    description=(
        "Search the user's Mac via Spotlight (the same index Cmd+Space "
        "uses). Use when the user asks 'find my taxes folder', 'where's "
        "the lease PDF?', 'show me recent screenshots'.\n\n"
        "Args:\n"
        "  query: What to search for. Spotlight matches filenames AND "
        "file contents.\n"
        "  kind: Filter by kind. One of: any (default), folder, app, "
        "pdf, image, document, music, movie.\n"
        "  in_folder: Optional path to scope the search to. Tilde is "
        "expanded. Useful for 'in Downloads' / 'in my projects folder'.\n"
        "  limit: Max results (default 5, max 20).\n\n"
        "Returns a numbered list of paths. To open one, follow up with "
        "`open_path` using the path string."
    ),
)
async def find_files(
    context: RunContext,
    query: str,
    kind: Kind = "any",
    in_folder: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> str:
    if msg := macos_only("Spotlight"):
        return msg
    if not query or not query.strip():
        return "No search query provided."

    limit = max(1, min(_MAX_LIMIT, int(limit)))

    args = ["mdfind"]
    if in_folder:
        scoped = os.path.expanduser(in_folder)
        if not os.path.isdir(scoped):
            return f"Folder does not exist: {scoped}"
        args += ["-onlyin", scoped]

    kind_filter = _KIND_MAP.get(kind, "")
    full_query = f"{query.strip()} {kind_filter}".strip()
    args.append(full_query)

    rc, out, err = await run_command(*args, timeout=10.0)
    if rc != 0:
        return f"Spotlight search failed: {err or 'unknown error'}"

    paths = [line for line in out.splitlines() if line.strip()][:limit]
    if not paths:
        return f"No results for '{query}'."

    lines = [f"{i + 1}. {p}" for i, p in enumerate(paths)]
    suffix = (
        f"\n(showing {len(paths)} of more)"
        if len(out.splitlines()) > limit
        else ""
    )
    return "Results:\n" + "\n".join(lines) + suffix


@function_tool(
    name="open_path",
    description=(
        "Open a file, folder, app, or URL using the macOS `open` "
        "command - the same handler invoked by double-clicking. Use "
        "when the user says 'open my Downloads folder', 'open that "
        "PDF', 'open github dot com', or after `find_files` to surface "
        "a result.\n\n"
        "Args:\n"
        "  path: A filesystem path (tilde expanded) OR a URL "
        "(http/https) OR an app name to launch (e.g. 'Calculator'). "
        "For paths, must exist; for URLs, opens in the default "
        "browser; for apps, equivalent to `open -a <name>`.\n"
        "  reveal: If true, reveals the path in Finder instead of "
        "opening it. Use for 'show me where X is'."
    ),
)
async def open_path(
    context: RunContext, path: str, reveal: bool = False
) -> str:
    if msg := macos_only("Open path"):
        return msg
    if not path or not path.strip():
        return "No path provided."

    p = path.strip()

    # URL? Pass through to `open` as-is.
    if p.startswith(("http://", "https://", "file://", "mailto:")):
        rc, _, err = await run_command("open", p, timeout=5.0)
        if rc != 0:
            return f"Failed to open URL: {err or 'unknown error'}"
        return f"Opened {p}."

    # Filesystem path?
    expanded = os.path.expanduser(p)
    if os.path.exists(expanded):
        args = ["open"]
        if reveal:
            args += ["-R"]
        args.append(expanded)
        rc, _, err = await run_command(*args, timeout=5.0)
        if rc != 0:
            return f"Failed to open {expanded}: {err or 'unknown error'}"
        verb = "Revealed" if reveal else "Opened"
        return f"{verb} {expanded}."

    # Treat as app name.
    rc, _, err = await run_command("open", "-a", p, timeout=5.0)
    if rc != 0:
        return (
            f"'{p}' is not a path, URL, or known app. "
            f"Try `find_files` to locate it first."
        )
    return f"Opened app '{p}'."


SPOTLIGHT_TOOLS = [find_files, open_path]

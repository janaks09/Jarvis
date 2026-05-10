"""Spotify control tools (macOS, via AppleScript).

Provides basic transport control for the Spotify desktop app.
No API keys required - these talk to the local app via `osascript`.

Limitations:
- Cannot access your library, search, or "Liked Songs" (use Web API for that).
- Requires the Spotify desktop app to be installed.
"""

import logging

from livekit.agents import function_tool, RunContext

from tools.mac.utils import macos_only, run_osascript

logger = logging.getLogger(__name__)


@function_tool(
    name="spotify_play",
    description="Resume / start playback in the Spotify desktop app on the user's Mac.",
)
async def spotify_play(context: RunContext) -> str:
    if msg := macos_only("Spotify"):
        return msg
    rc, _, err = await run_osascript('tell application "Spotify" to play')
    if rc != 0:
        return f"Failed to play Spotify: {err or 'unknown error'}"
    return "Spotify is playing."


@function_tool(
    name="spotify_pause",
    description="Pause playback in the Spotify desktop app.",
)
async def spotify_pause(context: RunContext) -> str:
    if msg := macos_only("Spotify"):
        return msg
    rc, _, err = await run_osascript('tell application "Spotify" to pause')
    if rc != 0:
        return f"Failed to pause Spotify: {err or 'unknown error'}"
    return "Spotify paused."


@function_tool(
    name="spotify_next",
    description="Skip to the next track in Spotify.",
)
async def spotify_next(context: RunContext) -> str:
    if msg := macos_only("Spotify"):
        return msg
    rc, _, err = await run_osascript('tell application "Spotify" to next track')
    if rc != 0:
        return f"Failed to skip track: {err or 'unknown error'}"
    return "Skipped to next track."


@function_tool(
    name="spotify_previous",
    description="Go back to the previous track in Spotify.",
)
async def spotify_previous(context: RunContext) -> str:
    if msg := macos_only("Spotify"):
        return msg
    # Spotify quirk: `previous track` once goes to start of current; calling twice goes to actual previous.
    rc, _, err = await run_osascript(
        'tell application "Spotify"\nprevious track\nprevious track\nend tell'
    )
    if rc != 0:
        return f"Failed to go to previous track: {err or 'unknown error'}"
    return "Went to previous track."


@function_tool(
    name="spotify_set_volume",
    description=(
        "Set Spotify playback volume. `level` must be an integer between 0 and 100."
    ),
)
async def spotify_set_volume(context: RunContext, level: int) -> str:
    if msg := macos_only("Spotify"):
        return msg
    try:
        level_int = int(level)
    except (TypeError, ValueError):
        return "Volume must be an integer between 0 and 100."
    level_int = max(0, min(100, level_int))
    rc, _, err = await run_osascript(
        f'tell application "Spotify" to set sound volume to {level_int}'
    )
    if rc != 0:
        return f"Failed to set volume: {err or 'unknown error'}"
    return f"Spotify volume set to {level_int}."


@function_tool(
    name="spotify_now_playing",
    description="Get the title and artist of the track currently playing in Spotify.",
)
async def spotify_now_playing(context: RunContext) -> str:
    if msg := macos_only("Spotify"):
        return msg
    script = (
        'tell application "Spotify"\n'
        'if it is running then\n'
        'set trackName to name of current track\n'
        'set artistName to artist of current track\n'
        'set albumName to album of current track\n'
        'set playerStateValue to player state as string\n'
        'return trackName & " || " & artistName & " || " & albumName & " || " & playerStateValue\n'
        'else\n'
        'return "not running"\n'
        'end if\n'
        'end tell'
    )
    rc, out, err = await run_osascript(script)
    if rc != 0:
        return f"Failed to read Spotify state: {err or 'unknown error'}"
    if out == "not running":
        return "Spotify is not running."
    parts = out.split(" || ")
    if len(parts) != 4:
        return f"Unexpected Spotify response: {out}"
    track, artist, album, state = parts
    return f"{state.capitalize()}: \"{track}\" by {artist} (album: {album})."


SPOTIFY_TOOLS = [
    spotify_play,
    spotify_pause,
    spotify_next,
    spotify_previous,
    spotify_set_volume,
    spotify_now_playing,
]

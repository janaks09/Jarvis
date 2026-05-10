"""Global media transport for macOS.

Targets whichever desktop player is currently active - Spotify or
Apple Music - so the user can say "pause" or "next track" without
specifying the app. If both are running, the one that's actively
playing wins; if neither is playing, the most recently used one is
preferred (Spotify first).

Limitations:
- Does NOT control browser-based media (YouTube in Chrome, etc.).
  macOS exposes hardware media-key events through a private framework
  that AppleScript cannot reach without a compiled helper.
- Apps must be already running. This tool will not launch them.
"""

import logging

from livekit.agents import RunContext, function_tool

from tools.mac.utils import macos_only, run_osascript

logger = logging.getLogger(__name__)

# Player state values returned by the AppleScript probe.
_STATE_PLAYING = "playing"
_STATE_PAUSED = "paused"
_STATE_STOPPED = "stopped"
_STATE_NOT_RUNNING = "not_running"


async def _player_state(app_name: str) -> str:
    """Return one of: playing, paused, stopped, not_running."""
    script = f'''
tell application "System Events"
    if not (exists (process "{app_name}")) then return "not_running"
end tell
tell application "{app_name}"
    try
        set s to player state as string
        return s
    on error
        return "stopped"
    end try
end tell
'''
    rc, out, _ = await run_osascript(script, timeout=5.0)
    if rc != 0:
        return _STATE_NOT_RUNNING
    out = out.strip().lower()
    if "play" in out:
        return _STATE_PLAYING
    if "paus" in out:
        return _STATE_PAUSED
    if "stop" in out:
        return _STATE_STOPPED
    if "not_running" in out or "not running" in out:
        return _STATE_NOT_RUNNING
    return _STATE_STOPPED


async def _pick_target() -> tuple[str | None, str]:
    """Choose which player to control. Returns (app_name, state).

    Preference order:
      1. The one currently playing (only one should be at a time).
      2. The one that's paused (resume it).
      3. None - neither is running.
    """
    spotify_state = await _player_state("Spotify")
    music_state = await _player_state("Music")

    for app, state in (("Spotify", spotify_state), ("Music", music_state)):
        if state == _STATE_PLAYING:
            return app, state
    for app, state in (("Spotify", spotify_state), ("Music", music_state)):
        if state == _STATE_PAUSED:
            return app, state
    return None, _STATE_NOT_RUNNING


async def _send(app: str, command: str) -> tuple[int, str]:
    rc, _, err = await run_osascript(
        f'tell application "{app}" to {command}', timeout=5.0
    )
    return rc, err


@function_tool(
    name="media_play_pause",
    description=(
        "Toggle play/pause on whichever Mac media player is currently "
        "active (Spotify or Apple Music). Use when the user says 'pause "
        "the music', 'pause it', 'resume', 'play', or 'play/pause' "
        "without naming a specific app.\n\n"
        "Picks the playing app first; if nothing is playing, resumes the "
        "paused one. Does NOT control browser audio (YouTube, etc.) - "
        "for those, the user must focus the browser tab and press space."
    ),
)
async def media_play_pause(context: RunContext) -> str:
    if msg := macos_only("Media control"):
        return msg

    app, state = await _pick_target()
    if app is None:
        return "Nothing is playing - neither Spotify nor Music is running."

    command = "pause" if state == _STATE_PLAYING else "play"
    rc, err = await _send(app, command)
    if rc != 0:
        return f"Failed to {command} {app}: {err or 'unknown error'}"
    verb = "Paused" if command == "pause" else "Resumed"
    return f"{verb} {app}."


@function_tool(
    name="media_next",
    description=(
        "Skip to the next track on whichever Mac media player is "
        "currently active (Spotify or Apple Music). Use when the user "
        "says 'next track', 'skip', 'next song'.\n\n"
        "Targets the playing app first, then falls back to the paused "
        "one. Returns an error if neither player is running."
    ),
)
async def media_next(context: RunContext) -> str:
    if msg := macos_only("Media control"):
        return msg

    app, _ = await _pick_target()
    if app is None:
        return "Nothing to skip - neither Spotify nor Music is running."
    rc, err = await _send(app, "next track")
    if rc != 0:
        return f"Failed to skip on {app}: {err or 'unknown error'}"
    return f"Skipped to next track on {app}."


@function_tool(
    name="media_previous",
    description=(
        "Go to the previous track on whichever Mac media player is "
        "currently active (Spotify or Apple Music). Use when the user "
        "says 'previous track', 'go back', 'last song'.\n\n"
        "Targets the playing app first, then the paused one. Returns an "
        "error if neither player is running."
    ),
)
async def media_previous(context: RunContext) -> str:
    if msg := macos_only("Media control"):
        return msg

    app, _ = await _pick_target()
    if app is None:
        return "Nothing to rewind - neither Spotify nor Music is running."
    # Spotify quirk: a single `previous track` restarts the current song;
    # calling it twice goes to the actual previous track.
    cmd = "previous track\nprevious track" if app == "Spotify" else "previous track"
    rc, _, err = await run_osascript(
        f'tell application "{app}"\n{cmd}\nend tell', timeout=5.0
    )
    if rc != 0:
        return f"Failed to go back on {app}: {err or 'unknown error'}"
    return f"Went to previous track on {app}."


@function_tool(
    name="media_now_playing",
    description=(
        "Report what's currently playing across Spotify and Apple Music. "
        "Use when the user asks 'what's playing?', 'what song is this?', "
        "or 'who's the artist?' without naming a specific app.\n\n"
        "Returns the title, artist, and album of the active track. If "
        "neither player is running, says so."
    ),
)
async def media_now_playing(context: RunContext) -> str:
    if msg := macos_only("Media control"):
        return msg

    app, state = await _pick_target()
    if app is None:
        return "Nothing is playing - neither Spotify nor Music is running."

    script = f'''
tell application "{app}"
    set trackName to name of current track
    set artistName to artist of current track
    set albumName to album of current track
    return trackName & " || " & artistName & " || " & albumName
end tell
'''
    rc, out, err = await run_osascript(script, timeout=5.0)
    if rc != 0:
        return f"Failed to read {app} state: {err or 'unknown error'}"
    parts = out.split(" || ")
    if len(parts) != 3:
        return f"Unexpected {app} response: {out}"
    track, artist, album = parts
    label = "Playing" if state == _STATE_PLAYING else "Paused"
    return f'{label} on {app}: "{track}" by {artist} (album: {album}).'


MEDIA_TOOLS = [
    media_play_pause,
    media_next,
    media_previous,
    media_now_playing,
]

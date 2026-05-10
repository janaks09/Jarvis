"""Window management for the frontmost macOS app.

Snap the focused window to a region of the screen (left/right half,
quadrants, fullscreen, center, maximize) and minimize / restore via
AppleScript + System Events. No third-party app required.

Caveats:
- macOS requires the host process (Terminal / your IDE / the Jarvis
  binary) to have **Accessibility** permission in
  System Settings → Privacy & Security → Accessibility. Without it,
  System Events cannot read or set window bounds.
- "Fullscreen" here means *maximized to the visible screen frame*,
  not the green-button native fullscreen Space (which can't be
  toggled reliably via AppleScript across macOS versions).
"""

import logging

from livekit.agents import RunContext, function_tool

from tools.mac.utils import macos_only, run_osascript

logger = logging.getLogger(__name__)

# Region presets. Values are (x_frac, y_frac, w_frac, h_frac) of the
# *visible* screen frame (excludes menu bar and Dock).
_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "left": (0.0, 0.0, 0.5, 1.0),
    "right": (0.5, 0.0, 0.5, 1.0),
    "top": (0.0, 0.0, 1.0, 0.5),
    "bottom": (0.0, 0.5, 1.0, 0.5),
    "top-left": (0.0, 0.0, 0.5, 0.5),
    "top-right": (0.5, 0.0, 0.5, 0.5),
    "bottom-left": (0.0, 0.5, 0.5, 0.5),
    "bottom-right": (0.5, 0.5, 0.5, 0.5),
    "fullscreen": (0.0, 0.0, 1.0, 1.0),
    "maximize": (0.0, 0.0, 1.0, 1.0),
    "center": (0.125, 0.1, 0.75, 0.8),
}

_ALIASES: dict[str, str] = {
    "left half": "left",
    "right half": "right",
    "top half": "top",
    "bottom half": "bottom",
    "upper half": "top",
    "lower half": "bottom",
    "full": "fullscreen",
    "full screen": "fullscreen",
    "max": "maximize",
    "centre": "center",
}


def _normalize_region(region: str) -> str | None:
    key = region.strip().lower()
    key = _ALIASES.get(key, key)
    return key if key in _REGIONS else None


_SNAP_SCRIPT_TEMPLATE = '''
tell application "Finder"
    set screenBounds to bounds of window of desktop
end tell

set screenX to item 1 of screenBounds
set screenY to item 2 of screenBounds
set screenW to (item 3 of screenBounds) - screenX
set screenH to (item 4 of screenBounds) - screenY

set targetX to screenX + (round (screenW * {fx}))
set targetY to screenY + (round (screenH * {fy}))
set targetW to round (screenW * {fw})
set targetH to round (screenH * {fh})

tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    tell window 1 of frontApp
        set position to {{targetX, targetY}}
        set size to {{targetW, targetH}}
    end tell
    return appName
end tell
'''


@function_tool(
    name="snap_window",
    description=(
        "Snap the currently focused (frontmost) macOS window to a region "
        "of the screen. Use this when the user says things like 'put this "
        "window on the left', 'snap to right half', 'maximize the window', "
        "'move to top-right corner', or 'center this window'.\n\n"
        "`region` must be one of: left, right, top, bottom, top-left, "
        "top-right, bottom-left, bottom-right, fullscreen, maximize, center. "
        "Common aliases like 'left half', 'full screen', 'centre' are also "
        "accepted.\n\n"
        "Acts on whatever window is frontmost at call time, not a named "
        "app. Requires Accessibility permission for the host process."
    ),
)
async def snap_window(context: RunContext, region: str) -> str:
    if msg := macos_only("Window snapping"):
        return msg

    key = _normalize_region(region)
    if key is None:
        valid = ", ".join(sorted(_REGIONS.keys()))
        return f"Unknown region '{region}'. Valid regions: {valid}."

    fx, fy, fw, fh = _REGIONS[key]
    script = _SNAP_SCRIPT_TEMPLATE.format(fx=fx, fy=fy, fw=fw, fh=fh)
    rc, out, err = await run_osascript(script)
    if rc != 0:
        if "not allowed assistive access" in err.lower() or "1002" in err:
            return (
                "Couldn't move the window - Accessibility permission is "
                "missing. Grant it in System Settings → Privacy & Security "
                "→ Accessibility."
            )
        logger.warning("snap_window failed: %s", err)
        return f"Failed to snap window: {err or 'unknown error'}"

    app = out or "frontmost app"
    return f"Snapped {app}'s window to {key}."


@function_tool(
    name="minimize_window",
    description=(
        "Minimize the currently focused macOS window to the Dock. Use when "
        "the user says 'minimize this', 'minimize the window', or 'send "
        "this to the dock'. Acts on the frontmost window."
    ),
)
async def minimize_window(context: RunContext) -> str:
    if msg := macos_only("Window minimize"):
        return msg
    script = (
        'tell application "System Events"\n'
        '  set frontApp to first application process whose frontmost is true\n'
        '  set value of attribute "AXMinimized" of window 1 of frontApp to true\n'
        '  return name of frontApp\n'
        'end tell'
    )
    rc, out, err = await run_osascript(script)
    if rc != 0:
        return f"Failed to minimize window: {err or 'unknown error'}"
    return f"Minimized {out or 'frontmost'} window."


WINDOW_TOOLS = [snap_window, minimize_window]

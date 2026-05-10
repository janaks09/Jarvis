"""macOS control tools.

Aggregates all mac-specific function tools into a single list so the
agent can register them with one import.
"""

from tools.mac.apps import open_mac_app
from tools.mac.browser import BROWSER_TOOLS
from tools.mac.calendar import CALENDAR_TOOLS
from tools.mac.clipboard import CLIPBOARD_TOOLS
from tools.mac.focus import FOCUS_TOOLS
from tools.mac.media import MEDIA_TOOLS
from tools.mac.meetings import MEETINGS_TOOLS
from tools.mac.messages import MESSAGES_TOOLS
from tools.mac.screenshot import SCREENSHOT_TOOLS
from tools.mac.shell import SHELL_TOOLS
from tools.mac.shortcuts import SHORTCUTS_TOOLS, prime_shortcut_cache
from tools.mac.spotify import SPOTIFY_TOOLS
from tools.mac.spotlight import SPOTLIGHT_TOOLS
from tools.mac.system import SYSTEM_TOOLS
from tools.mac.window import WINDOW_TOOLS

ALL_MAC_TOOLS = [
    open_mac_app,
    *SPOTIFY_TOOLS,
    *WINDOW_TOOLS,
    *SCREENSHOT_TOOLS,
    *MESSAGES_TOOLS,
    *SHELL_TOOLS,
    *MEDIA_TOOLS,
    *SHORTCUTS_TOOLS,
    *BROWSER_TOOLS,
    *SPOTLIGHT_TOOLS,
    *CALENDAR_TOOLS,
    *FOCUS_TOOLS,
    *SYSTEM_TOOLS,
    *CLIPBOARD_TOOLS,
    *MEETINGS_TOOLS,
]

__all__ = ["ALL_MAC_TOOLS", "prime_shortcut_cache"]

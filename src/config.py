"""User-facing configuration loaded from environment variables.

Centralizes the .env values used to personalize the assistant so
agent.py and the instructions module read from one place.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UserSettings:
    assistant_name: str
    assistant_greeting: str
    user_name: str
    country_name: str
    user_away_timeout: float | None  # seconds of silence before auto-mute; None disables


def get_user_settings() -> UserSettings:
    raw_timeout = os.getenv("USER_AWAY_TIMEOUT", "10")
    if raw_timeout.strip().lower() in ("", "0", "none", "off", "false"):
        user_away_timeout: float | None = None
    else:
        user_away_timeout = float(raw_timeout)

    return UserSettings(
        assistant_name=os.getenv("ASSISTANT_NAME", "Jarvis"),
        assistant_greeting=os.getenv("ASSISTANT_GREETING", "Hello There!"),
        user_name=os.getenv("USER_NAME", "User"),
        country_name=os.getenv("USER_COUNTRY", "Canada"),
        user_away_timeout=user_away_timeout,
    )

"""Wake-word / mute-state gate for the assistant's STT stream.

Replaces three stateful booleans in agent.py with a single state
machine. Decides whether a final transcript should be forwarded to the
agent or blanked.

States:
    LISTENING - normal, transcripts pass through.
    MUTED     - user said 'mute'; only 'unmute' or the wake word
                resumes listening.
    AWAY      - user-state event reported away; the wake word resumes
                listening.
"""

import logging
import re
from enum import Enum

logger = logging.getLogger(__name__)


class _Mode(Enum):
    LISTENING = "listening"
    MUTED = "muted"
    AWAY = "away"


class WakeWordGate:
    def __init__(self, assistant_name: str):
        name = assistant_name.lower()
        keywords = [name, f"hey {name}", f"hello {name}"]
        # Word-boundary match so the wake word doesn't fire inside other words.
        self._wake_re = re.compile(
            r"\b(?:" + "|".join(re.escape(k) for k in keywords) + r")\b",
            re.IGNORECASE,
        )
        self._mode = _Mode.LISTENING

    @property
    def is_muted(self) -> bool:
        return self._mode == _Mode.MUTED

    def mark_user_away(self) -> bool:
        """User-state event says 'away'. Returns True if state changed.

        Ignored while muted - muting is a stronger user intent and we
        don't want 'away' to override it.
        """
        if self._mode == _Mode.LISTENING:
            self._mode = _Mode.AWAY
            logger.info("user is away")
            return True
        return False

    def process_transcript(self, transcript: str) -> bool:
        """Decide whether a final transcript should reach the agent.

        Returns True to forward the transcript intact; False if the
        caller should blank `event.alternatives[0].text` before
        yielding (the event is still yielded so STT bookkeeping stays
        consistent).
        """
        clean = transcript.strip().rstrip(".").lower()

        # Explicit mute command - always swallowed.
        if clean == "mute":
            self._mode = _Mode.MUTED
            logger.info("Assistant muted")
            return False

        if self._mode == _Mode.MUTED:
            # Explicit unmute is consumed; LLM never sees the command.
            if "unmute" in transcript.lower():
                self._mode = _Mode.LISTENING
                return False
            # Wake word inside speech - drop the mute and pass through.
            if self._wake_re.search(transcript):
                self._mode = _Mode.LISTENING
                return True
            return False

        if self._mode == _Mode.AWAY:
            if self._wake_re.search(transcript):
                self._mode = _Mode.LISTENING
                return True
            return False

        return True

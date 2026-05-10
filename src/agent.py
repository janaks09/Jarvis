import asyncio
import logging
import typing as t
from livekit import rtc

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    AgentServer,
    JobContext,
    JobProcess,
    RoomInputOptions,
    cli,
    llm,
    UserStateChangedEvent,
)
from livekit.agents.llm import FunctionTool, RawFunctionTool
from livekit.agents.types import NOT_GIVEN
from livekit.agents.voice.agent import ModelSettings
from livekit.agents.llm import ChatContext, ChatChunk

from livekit.plugins import (
    noise_cancellation,
    silero,
    deepgram,
    anthropic,
    elevenlabs,
    openai,
    cartesia,
    google,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from config import UserSettings, get_user_settings
from tools.mac import ALL_MAC_TOOLS, prime_shortcut_cache
from tools.web_search_tools import search_web
from utils.instructions import (
    get_assistant_instructions,
    get_random_pre_action_message,
    get_random_wait_message,
)
from utils.wake_word import WakeWordGate

from google.genai import types as google_types

logger = logging.getLogger("agent")

load_dotenv(".env.local")


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


class Assistant(Agent):
    def __init__(self, settings: UserSettings) -> None:
        system_prompt = get_assistant_instructions(
            assistant_name=settings.assistant_name,
            user_name=settings.user_name,
            country_name=settings.country_name,
        )

        all_tools = [search_web, *ALL_MAC_TOOLS]

        super().__init__(
            instructions=system_prompt,
            tools=all_tools,
        )
        self.gate = WakeWordGate(settings.assistant_name)
        self._greeting = settings.assistant_greeting

        logger.info(f"Assistant initialized with {len(self.tools)} tools")

    async def on_enter(self):
        self.session.say(self._greeting)
        # self.session.generate_reply(
        #     instructions="Greet the user warmly. keep it brief."
        # )

    async def stt_node(
        self, text: t.AsyncIterable[str], model_settings: t.Optional[dict] = None
    ) -> t.Optional[t.AsyncIterable[rtc.AudioFrame]]:
        parent_stream = super().stt_node(text, model_settings)
        if parent_stream is None:
            return None

        async def process_stream():
            async for event in parent_stream:
                if (
                    hasattr(event, "type")
                    and str(event.type) == "SpeechEventType.FINAL_TRANSCRIPT"
                    and event.alternatives
                ):
                    transcript = event.alternatives[0].text
                    if not self.gate.process_transcript(transcript):
                        event.alternatives[0].text = ""
                yield event

        return process_stream()

    async def llm_node(
        self,
        chat_ctx: ChatContext,
        tools: list[FunctionTool | RawFunctionTool],
        model_settings: ModelSettings,
    ):
        session_llm = self.session.llm
        if isinstance(session_llm, llm.FallbackAdapter):
            is_anthropic = isinstance(session_llm._llm_instances[0], anthropic.LLM)
        else:
            is_anthropic = isinstance(session_llm, anthropic.LLM)

        async for chunk in super().llm_node(chat_ctx, tools, model_settings):
            if isinstance(chunk, ChatChunk) and chunk.delta and chunk.delta.tool_calls:
                for tool_call in chunk.delta.tool_calls:
                    if is_anthropic:
                        logger.info(
                            "Using Anthropic LLM - skipping pre-action messages."
                        )
                        continue
                    if any(
                        action_word in tool_call.name.lower()
                        for action_word in [
                            "create",
                            "update",
                            "set",
                            "change",
                            "add",
                            "delete",
                            "remove",
                            "schedule",
                        ]
                    ):
                        self.session.say(
                            get_random_pre_action_message(), add_to_chat_ctx=False
                        )
                    else:
                        self.session.say(
                            get_random_wait_message(), add_to_chat_ctx=False
                        )
            yield chunk


server = AgentServer()
server.setup_fnc = prewarm


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    settings = get_user_settings()
    assistant = Assistant(settings)

    session = AgentSession(
        user_away_timeout=settings.user_away_timeout,
        stt=deepgram.STT(),
        llm=llm.FallbackAdapter(
            [
                openai.LLM(
                    temperature=0.4,
                    _strict_tool_schema=False,
                ),
                anthropic.LLM(temperature=0.4),
                google.LLM(
                    temperature=0.4,
                    http_options=google_types.HttpOptions(timeout=10000),
                ),
            ]
        ),
        tts=cartesia.TTS(), #voice="c45bc5ec-dc68-4feb-8829-6e6b2748095d"
        # tts=elevenlabs.TTS(model="eleven_flash_v2_5", voice_id="Cz0K1kOv9tD8l0b5Qu53"),
        vad=ctx.proc.userdata["vad"],
        turn_handling={
            "turn_detection": MultilingualModel(),
            "endpointing": {"mode": "dynamic"},
            "preemptive_generation": {"enabled": True, "preemptive_tts": True},
        },
    )

    @session.on("user_state_changed")
    def _user_state_changed(ev: UserStateChangedEvent):
        if ev.new_state == "away":
            assistant.gate.mark_user_away()

    async def log_usage():
        logger.info(f"Usage: {session.usage.model_usage}")

    ctx.add_shutdown_callback(log_usage)

    # Warm the Shortcuts.app library cache in the background so the first
    # `run_shortcut` call doesn't pay the CLI cold start (~1-2s).
    asyncio.create_task(prime_shortcut_cache())

    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()


def main():
    cli.run_app(server)


if __name__ == "__main__":
    main()

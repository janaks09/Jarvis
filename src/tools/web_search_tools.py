"""Web search tool using Perplexity AI."""

import logging
from livekit.agents import function_tool, RunContext
from services.perplexity_service import PerplexityService

logger = logging.getLogger(__name__)

_perplexity_service: PerplexityService | None = None


def _get_service() -> PerplexityService:
    """Lazy-init so PERPLEXITY_API_KEY is read after .env is loaded."""
    global _perplexity_service
    if _perplexity_service is None:
        _perplexity_service = PerplexityService()
    return _perplexity_service


@function_tool(
    name="search_web",
    description="""Search the web for current information, recent events, or facts you don't know.

Use this tool when:
- User asks about recent events, news, or current information
- User asks "what's happening", "latest", "today", "recent", "current"
- Question requires up-to-date information (stock prices, weather, sports scores, etc.)
- You don't have knowledge about the topic
- User explicitly asks to "search", "look up", or "find information"

Examples of when to use:
- "What's the weather today?"
- "Latest news about AI"
- "Who won the game yesterday?"
- "Current price of Bitcoin"
- "What's happening in the world?"
- "Search for information about [topic]"

DO NOT use for:
- General knowledge questions you can answer
- Historical facts from before 2024
- Simple calculations or definitions""",
)
async def search_web(context: RunContext, query: str) -> str:
    """
    Search the web for current information using Perplexity AI.

    Args:
        context: RunContext from LiveKit (contains userdata)
        query: Search query or question

    Returns:
        Search results with answer and sources
    """
    try:

        result = await _get_service().search(query)

        answer = result["answer"]
        response = answer

        return response

    except Exception as e:

        logger.error(f"Error in web search tool: {e}")

        # Provide user-friendly error messages with actionable guidance
        error_str = str(e).lower()
        if "timeout" in error_str:
            return "The search is taking too long. Could you try rephrasing your question, or I can try again if you'd like?"
        elif "api" in error_str or "key" in error_str or "unauthorized" in error_str:
            return "I'm having trouble connecting to my search service right now. Please try asking again in a moment."
        elif "network" in error_str or "connection" in error_str:
            return "I'm having network connectivity issues. Could you try again in a moment?"
        else:
            return "I couldn't complete that search. Could you try rephrasing your question or ask something else?"

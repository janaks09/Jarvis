"""Perplexity API service for web search."""

import logging
import os
from typing import Any, Dict

import aiohttp

logger = logging.getLogger(__name__)


class PerplexityService:
    """
    Service to perform web searches using Perplexity API.
    Provides real-time, up-to-date information with citations.
    """

    def __init__(self):
        self.api_key = os.getenv("PERPLEXITY_API_KEY")
        self.api_url = "https://api.perplexity.ai/chat/completions"
        self.model = "sonar"

        if not self.api_key:
            logger.warning("PERPLEXITY_API_KEY not set in environment")

    async def search(self, query: str, max_tokens: int = 400) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "answer": "Web search is not configured. Please set PERPLEXITY_API_KEY.",
                "sources": [],
            }

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful person AI assistant providing current, accurate information. Keep responses conversational and under 1-3 sentences for voice delivery. Speak naturally as if talking to someone on the phone. Do not use markdown formatting. convert acronyms to full words (especially for weather and distance measurement).",
                    },
                    {"role": "user", "content": query},
                ],
                "temperature": 0.5,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        return {
                            "answer": f"Search failed with status {response.status}"
                        }

                    data = await response.json()
                    answer = data["choices"][0]["message"]["content"]

                    return {
                        "answer": answer,
                    }

        except aiohttp.ClientTimeout:
            logger.error(f"Perplexity API timeout for query: {query}")
            return {
                "answer": "Search request timed out. Please try again.",
            }
        except Exception as e:
            logger.error(f"Error performing web search: {e}")
            return {"answer": f"Search error: {str(e)}"}

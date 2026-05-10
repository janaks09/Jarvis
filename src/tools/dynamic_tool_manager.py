"""
Dynamic Tool Manager for LiveKit Voice Agent.

This module provides dynamic tool loading/unloading to reduce prompt token usage.
Instead of preloading all tools, it loads them on-demand based on user intent
and unloads them after a configurable number of turns.

Key Features:
- Tool categories with lazy loading
- Intent-based tool selection
- Automatic tool cleanup after N turns
- Custom tool support
"""

import os
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Any
from collections import defaultdict

from livekit.agents import llm, function_tool
from livekit.agents.llm import FunctionTool, RawFunctionTool

logger = logging.getLogger(__name__)


class ToolCategory(str, Enum):
    """Categories of tools that can be loaded dynamically."""

    CORE = "core"  # Always loaded (minimal set)
    CALENDAR = "calendar"
    EMAIL = "email"
    WEB_SEARCH = "web_search"
    CONTACTS = "contacts"
    TASKS = "tasks"
    NOTES = "notes"


@dataclass
class ToolUsage:
    """Track tool usage for automatic unloading."""

    category: ToolCategory
    loaded_at_turn: int
    last_used_turn: int
    use_count: int = 0


@dataclass
class ToolDefinition:
    """Definition of a tool that can be loaded dynamically."""

    category: ToolCategory
    loader: Callable[[], list[FunctionTool | RawFunctionTool]]
    keywords: list[str]  # Keywords to detect intent
    description: str


class DynamicToolManager:
    """
    Manages dynamic loading and unloading of tools based on context.

    Usage:
        manager = DynamicToolManager(turns_before_unload=3)
        manager.register_category(ToolCategory.CALENDAR, loader_fn, keywords=["calendar", "meeting"])

        # In llm_node or on user message:
        tools = manager.get_tools_for_intent("schedule a meeting tomorrow")

        # After each turn:
        manager.advance_turn()
    """

    def __init__(
        self,
        turns_before_unload: int = 3,
        max_active_categories: int = 3,
    ):
        """
        Initialize the dynamic tool manager.

        Args:
            turns_before_unload: Number of turns without use before unloading a tool category
            max_active_categories: Maximum number of tool categories to keep loaded
        """
        self.turns_before_unload = turns_before_unload
        self.max_active_categories = max_active_categories

        self._current_turn = 0
        self._tool_definitions: dict[ToolCategory, ToolDefinition] = {}
        self._loaded_tools: dict[ToolCategory, list[FunctionTool | RawFunctionTool]] = (
            {}
        )
        self._tool_usage: dict[ToolCategory, ToolUsage] = {}
        self._core_tools: list[FunctionTool | RawFunctionTool] = []

        # Intent detection cache
        self._category_keywords: dict[str, ToolCategory] = {}

    def register_core_tools(
        self,
        tools: list[FunctionTool | RawFunctionTool],
    ) -> None:
        """
        Register tools that should always be available.
        These are minimal tools that don't bloat the prompt.

        Args:
            tools: List of core tools to always include
        """
        self._core_tools = tools
        logger.info(f"Registered {len(tools)} core tools")

    def register_category(
        self,
        category: ToolCategory,
        loader: Callable[[], list[FunctionTool | RawFunctionTool]],
        keywords: list[str],
        description: str = "",
    ) -> None:
        """
        Register a tool category with its loader function.

        Args:
            category: The tool category
            loader: Function that returns the tools for this category (lazy loading)
            keywords: Keywords that indicate intent to use this category
            description: Human-readable description of the category
        """
        self._tool_definitions[category] = ToolDefinition(
            category=category,
            loader=loader,
            keywords=[kw.lower() for kw in keywords],
            description=description,
        )

        # Build keyword -> category mapping
        for keyword in keywords:
            self._category_keywords[keyword.lower()] = category

        logger.info(
            f"Registered tool category: {category.value} with {len(keywords)} keywords"
        )

    def detect_intent_categories(self, user_message: str) -> list[ToolCategory]:
        """
        Detect which tool categories are needed based on user message.

        Args:
            user_message: The user's message/query

        Returns:
            List of detected tool categories
        """
        detected: set[ToolCategory] = set()
        message_lower = user_message.lower()

        for keyword, category in self._category_keywords.items():
            if keyword in message_lower:
                detected.add(category)

        return list(detected)

    def load_category(
        self, category: ToolCategory
    ) -> list[FunctionTool | RawFunctionTool]:
        """
        Load tools for a specific category.

        Args:
            category: The category to load

        Returns:
            List of loaded tools
        """
        if category in self._loaded_tools:
            # Update usage
            if category in self._tool_usage:
                self._tool_usage[category].last_used_turn = self._current_turn
                self._tool_usage[category].use_count += 1
            return self._loaded_tools[category]

        if category not in self._tool_definitions:
            logger.warning(f"Unknown tool category: {category}")
            return []

        # Load tools lazily
        definition = self._tool_definitions[category]
        tools = definition.loader()

        self._loaded_tools[category] = tools
        self._tool_usage[category] = ToolUsage(
            category=category,
            loaded_at_turn=self._current_turn,
            last_used_turn=self._current_turn,
            use_count=1,
        )

        logger.info(f"Loaded {len(tools)} tools for category: {category.value}")
        return tools

    def unload_category(self, category: ToolCategory) -> None:
        """
        Unload tools for a specific category.

        Args:
            category: The category to unload
        """
        if category in self._loaded_tools:
            del self._loaded_tools[category]
        if category in self._tool_usage:
            del self._tool_usage[category]

        logger.info(f"Unloaded tool category: {category.value}")

    def get_tools_for_intent(
        self,
        user_message: str,
        force_categories: list[ToolCategory] | None = None,
    ) -> list[FunctionTool | RawFunctionTool]:
        """
        Get all tools relevant for the user's intent.

        Args:
            user_message: The user's message to analyze
            force_categories: Optional list of categories to force load

        Returns:
            List of relevant tools
        """
        # Start with core tools
        tools = list(self._core_tools)

        # Detect intent-based categories
        categories = self.detect_intent_categories(user_message)

        # Add forced categories
        if force_categories:
            categories.extend(force_categories)

        # Deduplicate
        categories = list(set(categories))

        # Enforce max categories limit
        if len(categories) > self.max_active_categories:
            # Keep most recently used categories
            categories = sorted(
                categories,
                key=lambda c: self._tool_usage.get(
                    c, ToolUsage(c, 0, 0)
                ).last_used_turn,
                reverse=True,
            )[: self.max_active_categories]

        # Load tools for detected categories
        for category in categories:
            category_tools = self.load_category(category)
            tools.extend(category_tools)

        logger.debug(
            f"Returning {len(tools)} tools for intent. Categories: {[c.value for c in categories]}"
        )
        return tools

    def get_active_tools(self) -> list[FunctionTool | RawFunctionTool]:
        """
        Get all currently loaded tools.

        Returns:
            List of all active tools
        """
        tools = list(self._core_tools)
        for category_tools in self._loaded_tools.values():
            tools.extend(category_tools)
        return tools

    def advance_turn(self) -> list[ToolCategory]:
        """
        Advance to the next conversation turn and cleanup unused tools.

        Returns:
            List of categories that were unloaded
        """
        self._current_turn += 1
        unloaded: list[ToolCategory] = []

        # Find categories to unload
        categories_to_unload = []
        for category, usage in self._tool_usage.items():
            turns_since_use = self._current_turn - usage.last_used_turn
            if turns_since_use >= self.turns_before_unload:
                categories_to_unload.append(category)

        # Unload stale categories
        for category in categories_to_unload:
            self.unload_category(category)
            unloaded.append(category)

        if unloaded:
            logger.info(
                f"Turn {self._current_turn}: Unloaded {len(unloaded)} stale categories: {[c.value for c in unloaded]}"
            )

        return unloaded

    def mark_tool_used(self, tool_name: str) -> None:
        """
        Mark a tool as used to prevent its category from being unloaded.

        Args:
            tool_name: The name of the tool that was used
        """
        # Find which category this tool belongs to
        for category, tools in self._loaded_tools.items():
            for tool in tools:
                if hasattr(tool, "__name__") and tool.__name__ == tool_name:
                    if category in self._tool_usage:
                        self._tool_usage[category].last_used_turn = self._current_turn
                        self._tool_usage[category].use_count += 1
                    return

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about tool loading.

        Returns:
            Dictionary with stats
        """
        total_loaded = sum(len(tools) for tools in self._loaded_tools.values())
        return {
            "current_turn": self._current_turn,
            "core_tools": len(self._core_tools),
            "loaded_categories": list(self._loaded_tools.keys()),
            "total_loaded_tools": total_loaded + len(self._core_tools),
            "usage": {
                cat.value: {
                    "loaded_at": usage.loaded_at_turn,
                    "last_used": usage.last_used_turn,
                    "use_count": usage.use_count,
                }
                for cat, usage in self._tool_usage.items()
            },
        }

    def reset(self) -> None:
        """Reset the manager state (useful for new sessions)."""
        self._current_turn = 0
        self._loaded_tools.clear()
        self._tool_usage.clear()
        logger.info("Reset dynamic tool manager state")


# Singleton instance for convenience
_default_manager: DynamicToolManager | None = None


def get_default_manager() -> DynamicToolManager:
    """Get or create the default tool manager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = DynamicToolManager()
    return _default_manager

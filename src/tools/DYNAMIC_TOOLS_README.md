# Dynamic Tool Loading for LiveKit Voice Agents

This module provides a dynamic tool loading system that reduces prompt token usage by loading tools on-demand based on user intent and automatically unloading them after a configurable number of conversation turns.

## The Problem

When you preload a large set of tools, the tool definitions are included in every prompt sent to the LLM. This results in:
- **High prompt token costs** - Each request includes full tool schemas
- **Slower response times** - More tokens = longer processing
- **Context window waste** - Tool definitions consume valuable context

## The Solution

Dynamic tool loading:
1. **Starts minimal** - Only core tools (like web search) are loaded initially
2. **Intent detection** - Analyzes user messages for keywords to determine which tool categories are needed
3. **Lazy loading** - Only loads tool categories when needed
4. **Auto-cleanup** - Unloads tool categories after N turns without use

## Usage

### Basic Integration (Already in agent.py)

The main `agent.py` wires up the manager:

```python
from tools.dynamic_tool_manager import DynamicToolManager, ToolCategory

class Assistant(Agent):
    def __init__(self, ...):
        # Initialize dynamic tool manager
        self.tool_manager = DynamicToolManager(
            turns_before_unload=3,  # Unload after 3 turns without use
            max_active_categories=3,  # Max categories to keep loaded
        )

        # Register core tools (always available)
        self.tool_manager.register_core_tools([search_web])

        # Initialize with only core tools
        super().__init__(
            instructions=system_prompt,
            tools=self.tool_manager.get_active_tools(),
        )
```

### Adding Custom Tools

Create your own tools and register them:

```python
from tools.dynamic_tool_manager import DynamicToolManager, ToolCategory
from livekit.agents import function_tool

@function_tool(
    name="my_custom_tool",
    description="Does something useful",
)
async def my_custom_tool(context, param: str) -> str:
    return f"Result for {param}"

# Register with manager
manager.register_category(
    category=ToolCategory.TASKS,  # Use existing or create new
    loader=lambda: [my_custom_tool],
    keywords=["keyword1", "keyword2", "keyword3"],
    description="My custom tools",
)
```

### Tool Categories

Built-in categories:
- `ToolCategory.CORE` - Always loaded (web search, etc.)
- `ToolCategory.CALENDAR` - Calendar tools
- `ToolCategory.EMAIL` - Email tools
- `ToolCategory.WEB_SEARCH` - Web search tools
- `ToolCategory.CONTACTS` - Contact management
- `ToolCategory.TASKS` - Task/todo management
- `ToolCategory.NOTES` - Note-taking

### Intent Detection Keywords

The system uses keyword matching to detect user intent:

**Calendar:**
```
calendar, schedule, meeting, appointment, event,
reschedule, cancel meeting, free time, availability,
book, slot, tomorrow, today's schedule
```

**Email:**
```
email, mail, send, inbox, draft, reply,
message, received, unread, compose
```

## How It Works

### 1. Initial State
```
[Core: search_web] → Only 1 tool in prompt
```

### 2. User: "Check my calendar for tomorrow"
```
Intent detected: calendar
Loading: CALENDAR category
[Core: search_web, Calendar: 9 tools] → 10 tools in prompt
```

### 3. User asks 3 unrelated questions
```
Turn counter: 3 turns since calendar was used
Auto-unload: CALENDAR category
[Core: search_web] → Back to 1 tool
```

### 4. User: "Send an email to John"
```
Intent detected: email
Loading: EMAIL category
[Core: search_web, Email: 11 tools] → 12 tools in prompt
```

## Configuration Options

```python
DynamicToolManager(
    turns_before_unload=3,    # Turns without use before unloading (default: 3)
    max_active_categories=3,  # Max categories to keep loaded (default: 3)
)
```

## Monitoring

Get stats on tool loading:

```python
stats = manager.get_stats()
print(stats)
# {
#     "current_turn": 5,
#     "core_tools": 1,
#     "loaded_categories": [ToolCategory.EMAIL],
#     "total_loaded_tools": 12,
#     "usage": {
#         "email": {"loaded_at": 3, "last_used": 5, "use_count": 2}
#     }
# }
```

## Files

- `src/tools/dynamic_tool_manager.py` - Main manager class
- `src/tools/custom_tools_example.py` - Example custom tools
- `src/agent.py` - Agent wiring

## Token Savings

| Scenario | Static Loading | Dynamic Loading | Savings |
|----------|----------------|-----------------|---------|
| Initial prompt | ~20 tools | 1 tool | ~95% |
| Calendar query | ~20 tools | 10 tools | ~50% |
| Mixed conversation | ~20 tools | 3-10 tools | 50-85% |

## Best Practices

1. **Keep core tools minimal** - Only include always-needed tools
2. **Use specific keywords** - Better intent detection = fewer false loads
3. **Adjust unload timing** - Higher for frequent tool users, lower for casual
4. **Monitor stats** - Log `get_stats()` to understand usage patterns
5. **Group related tools** - Categories should be logically grouped

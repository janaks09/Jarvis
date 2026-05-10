"""
Custom Tools Example for Dynamic Loading.

This module shows how to add your own custom tools that work with
the dynamic tool loading system. Simply create tool functions and
register them with the DynamicToolManager.
"""

from livekit.agents import function_tool, RunContext
from tools.dynamic_tool_manager import DynamicToolManager, ToolCategory


# Example: Custom task management tools
@function_tool(
    name="create_task",
    description="Create a new task or todo item with a title and optional due date.",
)
async def create_task(
    context: RunContext,
    title: str,
    due_date: str = "",
    priority: str = "medium",
) -> str:
    """
    Create a new task.
    
    Args:
        context: RunContext from LiveKit
        title: Title of the task
        due_date: Optional due date (e.g., "tomorrow", "next week")
        priority: Task priority (low, medium, high)
    
    Returns:
        Confirmation message
    """
    # Implement your task creation logic here
    # This is a placeholder that would connect to your task backend
    return f"Created task: '{title}' with priority {priority}" + (f", due {due_date}" if due_date else "")


@function_tool(
    name="list_tasks",
    description="List all pending tasks or todos.",
)
async def list_tasks(context: RunContext) -> str:
    """
    List all pending tasks.
    
    Args:
        context: RunContext from LiveKit
    
    Returns:
        List of tasks as formatted string
    """
    # Implement your task listing logic here
    # This is a placeholder
    return "Your tasks:\n1. Review meeting notes (high priority)\n2. Send weekly report (medium priority)"


@function_tool(
    name="complete_task",
    description="Mark a task as completed.",
)
async def complete_task(context: RunContext, task_id: str) -> str:
    """
    Mark a task as completed.
    
    Args:
        context: RunContext from LiveKit
        task_id: ID or name of the task to complete
    
    Returns:
        Confirmation message
    """
    # Implement your task completion logic here
    return f"Marked task '{task_id}' as completed!"


# Example: Custom note-taking tools
@function_tool(
    name="create_note",
    description="Create a new note with a title and content.",
)
async def create_note(
    context: RunContext,
    title: str,
    content: str,
) -> str:
    """
    Create a new note.
    
    Args:
        context: RunContext from LiveKit
        title: Title of the note
        content: Note content
    
    Returns:
        Confirmation message
    """
    # Implement your note creation logic here
    return f"Created note: '{title}'"


@function_tool(
    name="search_notes",
    description="Search through notes by keyword.",
)
async def search_notes(context: RunContext, query: str) -> str:
    """
    Search notes by keyword.
    
    Args:
        context: RunContext from LiveKit
        query: Search query
    
    Returns:
        Matching notes
    """
    # Implement your note search logic here
    return f"Found 0 notes matching '{query}'"


# Tool loaders for dynamic registration
def get_task_tools():
    """Get all task management tools."""
    return [create_task, list_tasks, complete_task]


def get_note_tools():
    """Get all note-taking tools."""
    return [create_note, search_notes]


# Keywords for intent detection
TASK_KEYWORDS = [
    "task", "todo", "reminder", "to-do", "tasks",
    "create task", "add task", "my tasks", "pending",
    "complete", "done", "finish", "checklist",
]

NOTE_KEYWORDS = [
    "note", "notes", "write down", "remember this",
    "save this", "memo", "jot down", "take note",
]


def register_custom_tools_with_manager(manager: DynamicToolManager):
    """
    Register custom tools with a DynamicToolManager.
    
    Call this to add task and note tools to your agent.
    
    Args:
        manager: DynamicToolManager instance
        
    Example:
        from tools.custom_tools_example import register_custom_tools_with_manager
        
        manager = DynamicToolManager()
        register_custom_tools_with_manager(manager)
    """
    # Register task tools
    manager.register_category(
        category=ToolCategory.TASKS,
        loader=get_task_tools,
        keywords=TASK_KEYWORDS,
        description="Task and todo management tools",
    )
    
    # Register note tools
    manager.register_category(
        category=ToolCategory.NOTES,
        loader=get_note_tools,
        keywords=NOTE_KEYWORDS,
        description="Note-taking and memo tools",
    )

"""
Tool & Capability Registry for Jarvis:
Provides structured metadata, schemas, parameter definitions,
permission levels, and direct deterministic execution for Jarvis tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Callable

from .app_registry import AppRegistry
from .safety_policy import SafetyPolicy
from .tools.browser_tool import BrowserTool
from .tools.computer_use import ComputerUseTool
from .tools.system_tool import SystemTool

log = logging.getLogger("tool_registry")


class ToolSafetyLevel(str, Enum):
    SAFE = "SAFE"                # Read-only or safe non-destructive actions (open browser, search)
    MODERATE = "MODERATE"        # Window closing, typing, hotkey simulation
    DANGEROUS = "DANGEROUS"      # File deletion, arbitrary shell commands


@dataclass
class ToolParameter:
    name: str
    type_name: str
    description: str
    required: bool = True
    default: Any = None


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: list[ToolParameter]
    safety_level: ToolSafetyLevel
    handler: Callable[..., dict[str, Any]]

    def to_schema(self) -> dict[str, Any]:
        """Export tool definition in OpenAPI / function calling schema."""
        properties = {}
        required_list = []
        for p in self.parameters:
            properties[p.name] = {
                "type": p.type_name,
                "description": p.description,
            }
            if p.required:
                required_list.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_list,
            },
            "safety_level": self.safety_level.value,
        }


class ToolRegistry:
    """
    Central Capability & Tool Registry.
    Provides Hermes Agent and Jarvis with first-class deterministic capabilities.
    """

    _instance: ToolRegistry | None = None

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    def __init__(self):
        self.tools: dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register_tool(self, tool: ToolDefinition) -> None:
        self.tools[tool.name] = tool
        log.debug("[TOOL_REGISTRY] Registered tool: %s (%s)", tool.name, tool.safety_level.value)

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self.tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self.tools.values())

    def get_all_schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self.tools.values()]

    def execute(self, tool_name: str, **kwargs) -> dict[str, Any]:
        """
        Execute a tool by name with parameter validation and safety checks.
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool not found in registry: {tool_name}"}

        # Evaluate safety policy
        allowed, reason = SafetyPolicy.evaluate_action(tool_name, kwargs)
        if not allowed:
            log.warning("[TOOL_REGISTRY] Safety policy blocked '%s': %s", tool_name, reason)
            return {"success": False, "error": f"Action blocked: {reason}"}

        try:
            log.info("[TOOL_REGISTRY] Executing '%s' with params: %s", tool_name, kwargs)
            result = tool.handler(**kwargs)
            return result
        except Exception as e:
            log.error("[TOOL_REGISTRY] Error executing '%s': %s", tool_name, e, exc_info=True)
            return {"success": False, "error": str(e)}

    # =========================================================================
    # TOOL HANDLERS IMPLEMENTATION
    # =========================================================================

    def _tool_open_application(self, app_name: str, path: str | None = None, args: list[str] | None = None) -> dict[str, Any]:
        """Open or launch a desktop application using the AppRegistry or path."""
        reg = AppRegistry.get_instance()
        matched = reg.find_by_exact_alias(app_name)

        target_name = matched.display_name if matched else app_name
        target_path = path or (matched.path if matched else None)

        if target_path and target_path.endswith(".lnk"):
            # Launch via Windows shortcut
            try:
                import os
                os.startfile(target_path)
                return {"success": True, "message": f"Launched {target_name} via shortcut.", "app": target_name}
            except Exception as e:
                log.debug("Shortcut launch failed, falling back to executable: %s", e)

        return ComputerUseTool.open_application(target_name, args)

    def _tool_close_application(self, app_name: str | None = None, hwnd: int | None = None) -> dict[str, Any]:
        """Close an application or active window."""
        return ComputerUseTool.close_window(app_name, hwnd=hwnd)

    def _tool_close_window(self, app_name: str | None = None, hwnd: int | None = None) -> dict[str, Any]:
        """Close an application or active window."""
        return ComputerUseTool.close_window(app_name, hwnd=hwnd)

    def _tool_maximize_window(self, app_name: str | None = None) -> dict[str, Any]:
        """Maximize the active user application window or specified application."""
        return ComputerUseTool.maximize_window(app_name)

    def _tool_minimize_window(self, app_name: str | None = None) -> dict[str, Any]:
        """Minimize the active user application window or specified application."""
        return ComputerUseTool.minimize_window(app_name)

    def _tool_restore_window(self, app_name: str | None = None) -> dict[str, Any]:
        """Restore a minimized or maximized window."""
        return ComputerUseTool.restore_window(app_name)

    def _tool_focus_application(self, app_name: str | None = None, index: int | None = None) -> dict[str, Any]:
        """Focus/switch to application window."""
        return ComputerUseTool.switch_window(app_name or "", index=index)

    def _tool_switch_window(self, app_name: str | None = None, index: int | None = None) -> dict[str, Any]:
        """Switch focus to application window."""
        return ComputerUseTool.switch_window(app_name or "", index=index)

    def _tool_type_text(self, text: str) -> dict[str, Any]:
        """Type text into active application window."""
        return ComputerUseTool.type_text(text)

    def _tool_press_hotkey(self, hotkey: str) -> dict[str, Any]:
        """Simulate pressing keyboard shortcut."""
        return ComputerUseTool.press_hotkey(hotkey)

    def _tool_search_web(self, query: str, engine: str = "google") -> dict[str, Any]:
        """Search the web via browser."""
        return BrowserTool.search_web(query, engine)

    def _tool_open_url(self, url: str, new_window: bool = False) -> dict[str, Any]:
        """Open web URL in browser."""
        return BrowserTool.open_url(url, new_window)

    def _tool_snap_window(self, position: str = "left") -> dict[str, Any]:
        """Snap window to layout position."""
        return ComputerUseTool.snap_window(position)

    def _tool_manage_tab(self, action: str = "next", index: int | None = None) -> dict[str, Any]:
        """Manage browser/app tabs."""
        return ComputerUseTool.manage_tab(action, index)

    def _tool_scroll_page(self, direction: str = "down", amount: int = 6) -> dict[str, Any]:
        """Scroll active window or webpage up/down."""
        return ComputerUseTool.scroll_page(direction, amount)

    def _tool_get_system_status(self) -> dict[str, Any]:
        """Retrieve CPU, RAM, disk metrics."""
        return SystemTool.get_system_status()

    def _tool_find_latest_file(self, folder: str = "Downloads", extension: str | None = None) -> dict[str, Any]:
        """Find latest file in folder."""
        return SystemTool.find_latest_file(folder, extension)

    def _tool_search_memory(self, query: str, limit: int = 5, category: str | None = None) -> dict[str, Any]:
        """Search long term memory in Qdrant."""
        from .memory.memory_service import get_memory_service
        items = get_memory_service().search(query, limit=limit, category=category)
        return {
            "success": True,
            "count": len(items),
            "memories": [it.to_dict() for it in items],
        }

    def _tool_store_memory(self, text: str, category: str = "general") -> dict[str, Any]:
        """Store fact or preference in Qdrant long term memory."""
        from .memory.memory_service import get_memory_service
        item_id = get_memory_service().store(text, category=category)
        return {
            "success": True,
            "id": item_id,
            "message": "Memory stored successfully.",
        }

    def _tool_resolve_and_click_target(self, query: str, action: str = "open", app_name: str = "chrome") -> dict[str, Any]:
        """Resolve and interact with UI target using Hermes Visual Perception Engine."""
        return ComputerUseTool.resolve_and_click_target(query, action, app_name)

    def _tool_select_youtube_video(self, index: int = 1, application: str = "chrome", wait_load: bool = True) -> dict[str, Any]:
        """Select or play the N-th YouTube video using row-major ordering and safe click region."""
        return ComputerUseTool.select_youtube_video(index=index, application=application, wait_load=wait_load)

    def _register_default_tools(self) -> None:
        """Register all default tools."""
        self.register_tool(ToolDefinition(
            name="open_application",
            description="Launch or open a desktop application (e.g. Visual Studio Code, Google Chrome, Spotify, Cursor).",
            parameters=[
                ToolParameter("app_name", "string", "Name or alias of the application to open"),
                ToolParameter("path", "string", "Optional explicit file or shortcut path", required=False),
                ToolParameter("args", "array", "Optional list of command line arguments", required=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_open_application,
        ))

        self.register_tool(ToolDefinition(
            name="close_application",
            description="Close a running application or the active foreground window.",
            parameters=[
                ToolParameter("app_name", "string", "Name of the application to close, or None for current active window", required=False),
            ],
            safety_level=ToolSafetyLevel.MODERATE,
            handler=self._tool_close_application,
        ))

        self.register_tool(ToolDefinition(
            name="close_window",
            description="Close a running application or the active foreground window.",
            parameters=[
                ToolParameter("app_name", "string", "Name of the application to close, or None for current active window", required=False),
            ],
            safety_level=ToolSafetyLevel.MODERATE,
            handler=self._tool_close_window,
        ))

        self.register_tool(ToolDefinition(
            name="maximize_window",
            description="Maximize the active user application window or specified application window.",
            parameters=[
                ToolParameter("app_name", "string", "Optional name of application to maximize", required=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_maximize_window,
        ))

        self.register_tool(ToolDefinition(
            name="minimize_window",
            description="Minimize the active user application window or specified application window.",
            parameters=[
                ToolParameter("app_name", "string", "Optional name of application to minimize", required=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_minimize_window,
        ))

        self.register_tool(ToolDefinition(
            name="restore_window",
            description="Restore a minimized or maximized application window to its normal state.",
            parameters=[
                ToolParameter("app_name", "string", "Optional name of application to restore", required=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_restore_window,
        ))

        self.register_tool(ToolDefinition(
            name="focus_application",
            description="Bring an existing application window to the foreground / switch window.",
            parameters=[
                ToolParameter("app_name", "string", "Name of the application to bring to front, or None for Alt+Tab", required=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_focus_application,
        ))

        self.register_tool(ToolDefinition(
            name="switch_window",
            description="Bring an existing application window to the foreground / switch window.",
            parameters=[
                ToolParameter("app_name", "string", "Name of the application to switch to, or None for Alt+Tab", required=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_switch_window,
        ))

        self.register_tool(ToolDefinition(
            name="type_text",
            description="Type text into the active application window.",
            parameters=[
                ToolParameter("text", "string", "The text to type"),
            ],
            safety_level=ToolSafetyLevel.MODERATE,
            handler=self._tool_type_text,
        ))

        self.register_tool(ToolDefinition(
            name="press_hotkey",
            description="Press key combinations (e.g. 'ctrl+t', 'ctrl+w', 'enter', 'f11', 'esc').",
            parameters=[
                ToolParameter("hotkey", "string", "Key combination to press"),
            ],
            safety_level=ToolSafetyLevel.MODERATE,
            handler=self._tool_press_hotkey,
        ))

        self.register_tool(ToolDefinition(
            name="search_web",
            description="Search the web for a query using Google, YouTube, or Bing.",
            parameters=[
                ToolParameter("query", "string", "The search query"),
                ToolParameter("engine", "string", "Search engine: 'google', 'youtube', or 'bing'", required=False, default="google"),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_search_web,
        ))

        self.register_tool(ToolDefinition(
            name="open_url",
            description="Navigate to a specific URL in Google Chrome or default browser.",
            parameters=[
                ToolParameter("url", "string", "The URL to open"),
                ToolParameter("new_window", "boolean", "Whether to open in a new window", required=False, default=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_open_url,
        ))

        self.register_tool(ToolDefinition(
            name="snap_window",
            description="Snap active window to screen layout: 'left', 'right', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'center'.",
            parameters=[
                ToolParameter("position", "string", "Layout position name"),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_snap_window,
        ))

        self.register_tool(ToolDefinition(
            name="manage_tab",
            description="Control browser tabs: 'next', 'previous', 'new', 'close', 'reopen', 'select'.",
            parameters=[
                ToolParameter("action", "string", "Tab action name"),
                ToolParameter("index", "integer", "Tab index (1-9) for select action", required=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_manage_tab,
        ))

        self.register_tool(ToolDefinition(
            name="scroll_page",
            description="Scroll or roll active window, webpage, or YouTube feed: 'down', 'up', 'top', 'bottom'.",
            parameters=[
                ToolParameter("direction", "string", "Direction to scroll: 'down', 'up', 'top', 'bottom'", required=False, default="down"),
                ToolParameter("amount", "integer", "Number of scroll notches (default 6)", required=False, default=6),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_scroll_page,
        ))

        self.register_tool(ToolDefinition(
            name="get_system_status",
            description="Inspect system health, CPU, memory, disk, and battery telemetry.",
            parameters=[],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_get_system_status,
        ))

        self.register_tool(ToolDefinition(
            name="find_latest_file",
            description="Find the latest downloaded or created file in user folders.",
            parameters=[
                ToolParameter("folder", "string", "Folder name: 'Downloads', 'Documents', 'Desktop'", required=False, default="Downloads"),
                ToolParameter("extension", "string", "Optional file extension like 'pdf', 'png', 'zip'", required=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_find_latest_file,
        ))

        self.register_tool(ToolDefinition(
            name="search_memory",
            description="Recall relevant contextual information, user preferences, or facts from Qdrant long-term memory.",
            parameters=[
                ToolParameter("query", "string", "Semantic search query"),
                ToolParameter("limit", "integer", "Maximum items to return", required=False, default=5),
                ToolParameter("category", "string", "Optional category filter ('preference', 'project', 'fact')", required=False),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_search_memory,
        ))

        self.register_tool(ToolDefinition(
            name="store_memory",
            description="Save an important fact, user preference, or project context into Qdrant long-term memory.",
            parameters=[
                ToolParameter("text", "string", "The memory content to store"),
                ToolParameter("category", "string", "Category ('preference', 'project', 'fact')", required=False, default="general"),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_store_memory,
        ))

        self.register_tool(ToolDefinition(
            name="resolve_and_click_target",
            description="Perceive active UI window, resolve target object (video card, playlist, sidebar item, button, etc.), and click safe interaction point.",
            parameters=[
                ToolParameter("query", "string", "User target description (e.g. 'video thứ 3 hàng đầu', 'video thứ 2 trong Shorts', 'nút ba chấm video 2')"),
                ToolParameter("action", "string", "Action type: 'open', 'open_menu', 'focus', 'click'", required=False, default="open"),
                ToolParameter("app_name", "string", "Target application (e.g. 'chrome')", required=False, default="chrome"),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_resolve_and_click_target,
        ))

        self.register_tool(ToolDefinition(
            name="select_youtube_video",
            description="Select and play a YouTube video by its 1-based row-major visual ordinal.",
            parameters=[
                ToolParameter("index", "integer", "1-based visual index of video to select (e.g. 1 for 1st, 2 for 2nd)", required=False, default=1),
                ToolParameter("application", "string", "Target browser application (default 'chrome')", required=False, default="chrome"),
            ],
            safety_level=ToolSafetyLevel.SAFE,
            handler=self._tool_select_youtube_video,
        ))


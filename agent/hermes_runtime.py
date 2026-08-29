"""
Hermes Agent Runtime Engine:
Executes the agent loop, reasoning with Qwen LLM, planning, tool selection,
and computer-use operations with event streaming and structured entity interpretation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Callable

from .agent_events import AgentEvent, EventType
from .app_registry import AppRegistry
from .base_client import AgentResponse
from .llm.qwen_provider import LLMPlanResult, QwenProvider, get_llm_provider
from .normalizer import InterpretationContext, VoiceNormalizationPipeline
from .tool_registry import ToolRegistry
from .tools.browser_tool import BrowserTool
from .tools.computer_use import ComputerUseTool
from .tools.system_tool import SystemTool
from .voice_memory import VoiceMemory

log = logging.getLogger("hermes_runtime")


class HermesRuntime:
    """
    Independent Agent Runtime based on Hermes Agent architecture.
    Handles Qwen LLM reasoning, planning, tool dispatching, execution monitoring, and response synthesis.
    """

    def __init__(self):
        self.api_url = os.environ.get("HERMES_API_URL", "").strip()
        self.api_key = os.environ.get("HERMES_API_KEY", os.environ.get("OPENAI_API_KEY", "")).strip()
        self.model = os.environ.get("HERMES_MODEL", "hermes-3-llama-3.1-8b").strip()
        self.enabled = os.environ.get("HERMES_ENABLED", "True").strip().lower() in ("true", "1", "yes")

        # Active sessions tracking
        self.active_sessions: set[str] = set()
        self.tool_registry = ToolRegistry.get_instance()
        self.qwen_provider = get_llm_provider()

    def start_session(self, session_id: str) -> bool:
        self.active_sessions.add(session_id)
        log.info("[HERMES_RUNTIME] Session started: %s", session_id)
        return True

    def cancel_session(self, session_id: str) -> None:
        self.active_sessions.discard(session_id)
        log.info("[HERMES_RUNTIME] Session canceled: %s", session_id)

    def close_session(self, session_id: str) -> None:
        self.active_sessions.discard(session_id)
        log.info("[HERMES_RUNTIME] Session closed: %s", session_id)

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch tool execution through ToolRegistry or fallback tools."""
        return self._execute_tool_sync(tool_name, params)

    def _execute_tool_sync(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Synchronous wrapper for tool execution."""
        # 1. Try ToolRegistry
        if self.tool_registry.get_tool(tool_name):
            return self.tool_registry.execute(tool_name, **params)

        # 2. ComputerUseTool / BrowserTool Fallbacks
        if tool_name == "open_application":
            return ComputerUseTool.open_application(params.get("app_name", ""), params.get("args"))
        elif tool_name == "search_web":
            return BrowserTool.search_web(params.get("query", ""), params.get("engine", "google"))
        elif tool_name == "open_url":
            return BrowserTool.open_url(params.get("url", ""), params.get("new_window", False))
        elif tool_name == "switch_window":
            return ComputerUseTool.switch_window(params.get("app_name"))
        elif tool_name == "close_window":
            return ComputerUseTool.close_window(params.get("app_name"))
        elif tool_name == "minimize_window":
            return ComputerUseTool.minimize_window()
        elif tool_name == "maximize_window":
            return ComputerUseTool.maximize_window()
        elif tool_name in ("scroll_page", "scroll_window", "scroll_down", "scroll_up", "roll_page", "roll_down", "roll_up"):
            return ComputerUseTool.scroll_page(params.get("direction", "down"), params.get("amount", 6))
        elif tool_name == "select_youtube_video":
            return ComputerUseTool.select_youtube_video(params.get("index", 1))
        elif tool_name in ("resolve_and_click_target", "ui_interact"):
            return ComputerUseTool.resolve_and_click_target(
                query=params.get("query", ""),
                action=params.get("action", "open"),
                app_name=params.get("app_name", "chrome"),
            )
        elif tool_name == "click_coordinate":
            return ComputerUseTool.click_coordinate(params.get("x_ratio", 0.5), params.get("y_ratio", 0.5), params.get("click_count", 1))
        elif tool_name == "click_entity":
            return ComputerUseTool.click_entity(params.get("entity_name", "video_1"), params.get("app_name", "chrome"))
        elif tool_name == "type_text":
            return ComputerUseTool.type_text(params.get("text", ""))
        elif tool_name == "search_in_active_window":
            return ComputerUseTool.search_in_active_window(params.get("query", ""))
        elif tool_name == "paste_and_enter":
            return ComputerUseTool.paste_and_enter(params.get("text", ""))
        elif tool_name == "get_active_window_context":
            return ComputerUseTool.get_active_window_context()
        elif tool_name == "snap_window":
            return ComputerUseTool.snap_window(params.get("position", "left"))
        elif tool_name == "manage_tab":
            return ComputerUseTool.manage_tab(params.get("action", "next"), params.get("index"))
        elif tool_name == "press_hotkey":
            return ComputerUseTool.press_hotkey(params.get("hotkey", ""))
        elif tool_name == "find_latest_file":
            return SystemTool.find_latest_file(params.get("folder", "Downloads"), params.get("extension"))
        elif tool_name == "get_system_status":
            return SystemTool.get_system_status()
        elif tool_name == "run_powershell":
            return ComputerUseTool.run_powershell(params.get("command", ""))
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    async def run_plan(
        self,
        session_id: str,
        instruction: str,
        event_cb: Callable[[AgentEvent], None] | None = None,
        interpretation_context: InterpretationContext | dict[str, Any] | None = None,
    ) -> AgentResponse:
        """
        Reason about user instruction with Qwen LLM, execute tools, and synthesize English voice response.
        """
        def emit(evt_type: EventType, payload: dict[str, Any] | None = None):
            if event_cb:
                event = AgentEvent(
                    session_id=session_id,
                    event_type=evt_type,
                    payload=payload or {},
                    timestamp=time.time(),
                )
                try:
                    event_cb(event)
                except Exception as e:
                    log.warning("[HERMES_RUNTIME] Error in event callback: %s", e)

        emit(EventType.AGENT_STARTED, {"instruction": instruction})
        emit(EventType.AGENT_THINKING, {"status": "Analyzing request with Qwen reasoning..."})

        # Plan the actions needed for the instruction
        plan = self._plan_instruction(instruction, interpretation_context=interpretation_context)
        log.info("[HERMES_RUNTIME] Generated plan for '%s': %s", instruction, [p["tool"] for p in plan["actions"]])

        executed_tools = []
        for step in plan["actions"]:
            tool_name = step["tool"]
            params = step["params"]

            emit(EventType.AGENT_TOOL_STARTED, {"tool": tool_name, "params": params})
            log.info("[HERMES_RUNTIME] Executing tool: %s (%s)", tool_name, params)

            # Execute tool in executor to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, lambda: self._execute_tool_sync(tool_name, params))
            executed_tools.append({"tool": tool_name, "params": params, "result": result})

            emit(EventType.AGENT_TOOL_FINISHED, {"tool": tool_name, "result": result})

        emit(EventType.AGENT_VERIFYING, {"status": "Verifying execution results..."})

        reply_text = plan.get("speech_response", "Task completed, sir.")
        emit(EventType.AGENT_COMPLETED, {"response": reply_text, "tools_count": len(executed_tools)})

        return AgentResponse(
            session_id=session_id,
            text=reply_text,
            success=True,
            tools_executed=executed_tools,
        )

    def _plan_instruction(
        self,
        text: str,
        interpretation_context: InterpretationContext | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Intelligent intent reasoning, Qwen LLM planning, and multi-step plan generation.
        """
        # 0. Obtain InterpretationContext
        if interpretation_context is None:
            ctx = VoiceNormalizationPipeline.get_instance().process_transcript(text)
        elif isinstance(interpretation_context, dict):
            ctx = VoiceNormalizationPipeline.get_instance().process_transcript(
                interpretation_context.get("raw_transcript", text)
            )
        else:
            ctx = interpretation_context

        # 0.1 Check if clarification is needed (ambiguous / low confidence)
        if ctx.clarification_needed and ctx.clarification_prompt:
            log.info("[HERMES_RUNTIME] Ambiguity detected in '%s' -> Clarification needed: %s", text, ctx.clarification_prompt)
            return {
                "actions": [],
                "speech_response": ctx.clarification_prompt,
            }

        # 0.2 Try Qwen LLM Reasoning if available and configured
        if self.qwen_provider.is_available():
            try:
                llm_plan = self.qwen_provider.generate_plan(
                    instruction=ctx.normalized_transcript or text,
                    available_tools=self.tool_registry.get_all_schemas(),
                    context=ctx.to_dict(),
                )
                if llm_plan is not None and (llm_plan.actions or llm_plan.speech_response):
                    return {
                        "actions": llm_plan.actions,
                        "speech_response": llm_plan.speech_response,
                    }
            except Exception as e:
                log.debug("[HERMES_RUNTIME] Qwen LLM reasoning fallback to rule planner: %s", e)

        # 0.3 Check Voice Memory for direct overrides
        normalized, was_corrected = VoiceMemory.get_instance().normalize(ctx.normalized_transcript or text)
        cleaned = normalized.strip().lower()

        # 0.4 Compound Command Clause Decomposition (e.g. "đóng cửa sổ, chuyển tab", "đóng cửa sổ và mở chrome")
        split_pattern = r",|\s+và\s+|\s+then\s+|\s+rồi\s+|\s+sau đó\s+|\s+and\s+"
        clauses = [c.strip() for c in re.split(split_pattern, cleaned) if c.strip()]
        is_search = any(k in cleaned for k in ("search", "tìm", "google", "look up", "tra cứu"))
        is_youtube_select = "youtube" in cleaned and any(k in cleaned for k in ("select", "chọn", "video"))
        if len(clauses) > 1 and not is_search and not is_youtube_select:
            compound_actions: list[dict[str, Any]] = []
            speech_parts: list[str] = []
            for clause in clauses:
                sub_ctx = VoiceNormalizationPipeline.get_instance().process_transcript(clause)
                sub_plan = self._plan_single_action(clause, sub_ctx)
                if sub_plan and sub_plan.get("actions"):
                    compound_actions.extend(sub_plan["actions"])
                    if sub_plan.get("speech_response"):
                        speech_parts.append(sub_plan["speech_response"])
            if compound_actions:
                combined_speech = " ".join(speech_parts) if speech_parts else "Executing actions."
                return {
                    "actions": compound_actions,
                    "speech_response": combined_speech,
                }

        return self._plan_single_action(cleaned, ctx)

    def _plan_single_action(self, cleaned: str, ctx: InterpretationContext) -> dict[str, Any]:
        """Internal rule planner for a single instruction clause."""
        actions: list[dict[str, Any]] = []

        # 1. Compound Command Reasoning: e.g. "open VS Code and open the project from yesterday"
        if ctx.is_compound and ctx.target_entity and ctx.intent == "OPEN_APPLICATION" and any(k in cleaned for k in ("project", "dự án", "yesterday", "hôm qua", "recent")):
            app_name = ctx.target_entity.name
            actions.append({
                "tool": "open_application",
                "params": {"app_name": app_name}
            })
            actions.append({
                "tool": "find_latest_file",
                "params": {"folder": "Documents"}
            })
            return {
                "actions": actions,
                "speech_response": f"Opening {app_name} and locating your recent project, sir.",
            }

        # 2. Tab Navigation & Management
        if "next_tab" in cleaned or "next tab" in cleaned or "tab tiep theo" in cleaned or "chuyen tab" in cleaned:
            actions.append({"tool": "manage_tab", "params": {"action": "next"}})
            return {"actions": actions, "speech_response": "Switched to next tab."}

        if "previous_tab" in cleaned or "previous tab" in cleaned or "tab truoc" in cleaned or "quay lai tab" in cleaned:
            actions.append({"tool": "manage_tab", "params": {"action": "previous"}})
            return {"actions": actions, "speech_response": "Switched to previous tab."}

        if "new_tab" in cleaned or "new tab" in cleaned or "mo tab moi" in cleaned or "tao tab" in cleaned:
            actions.append({"tool": "manage_tab", "params": {"action": "new"}})
            return {"actions": actions, "speech_response": "Opened new tab."}

        if "reopen_tab" in cleaned or "reopen tab" in cleaned or "khoi phuc tab" in cleaned or "mo lai tab" in cleaned:
            actions.append({"tool": "manage_tab", "params": {"action": "reopen"}})
            return {"actions": actions, "speech_response": "Reopened closed tab."}

        tab_select_match = re.search(r"(?:select_tab_|select\s+tab\s+|chọn\s+tab\s+|tab\s+)(\d+|dau\s+tien|first|second|thu\s+hai|thu\s+2|thu\s+3|third|last|cuoi)", cleaned)
        if tab_select_match:
            raw_val = tab_select_match.group(1).strip()
            idx = 1
            if raw_val in ("1", "dau tien", "first", "thu 1", "thu nhat"):
                idx = 1
            elif raw_val in ("2", "second", "thu hai", "thu 2"):
                idx = 2
            elif raw_val in ("3", "third", "thu ba", "thu 3"):
                idx = 3
            elif raw_val in ("4", "fourth", "thu bon", "thu 4"):
                idx = 4
            elif raw_val in ("last", "cuoi", "cuoi cung"):
                idx = 9
            elif raw_val.isdigit():
                idx = int(raw_val)

            actions.append({"tool": "manage_tab", "params": {"action": "select", "index": idx}})
            return {"actions": actions, "speech_response": f"Switched to tab {idx}."}

        # 3. Window Snapping / Positioning (Top-Left, Top-Right, Bottom-Left, Bottom-Right, Split)
        if "top_right" in cleaned or "top right" in cleaned or "tren ben phai" in cleaned or "goc tren ben phai" in cleaned:
            actions.append({"tool": "snap_window", "params": {"position": "top_right"}})
            return {"actions": actions, "speech_response": "Snapped window to top right."}

        if "top_left" in cleaned or "top left" in cleaned or "tren ben trai" in cleaned or "goc tren ben trai" in cleaned:
            actions.append({"tool": "snap_window", "params": {"position": "top_left"}})
            return {"actions": actions, "speech_response": "Snapped window to top left."}

        if "bottom_right" in cleaned or "bottom right" in cleaned or "duoi ben phai" in cleaned or "goc duoi ben phai" in cleaned:
            actions.append({"tool": "snap_window", "params": {"position": "bottom_right"}})
            return {"actions": actions, "speech_response": "Snapped window to bottom right."}

        if "bottom_left" in cleaned or "bottom left" in cleaned or "duoi ben trai" in cleaned or "goc duoi ben trai" in cleaned:
            actions.append({"tool": "snap_window", "params": {"position": "bottom_left"}})
            return {"actions": actions, "speech_response": "Snapped window to bottom left."}

        if "snap_left" in cleaned or "snap left" in cleaned or "keo sang trai" in cleaned or "nua trai" in cleaned or "chia doi sang trai" in cleaned or "half left" in cleaned or "half screen left" in cleaned or "split left" in cleaned or "left half" in cleaned:
            actions.append({"tool": "snap_window", "params": {"position": "left"}})
            return {"actions": actions, "speech_response": "Snapped window to left half."}

        if "snap_right" in cleaned or "snap right" in cleaned or "keo sang phai" in cleaned or "nua phai" in cleaned or "chia doi sang phai" in cleaned or "half right" in cleaned or "half screen right" in cleaned or "split right" in cleaned or "right half" in cleaned:
            actions.append({"tool": "snap_window", "params": {"position": "right"}})
            return {"actions": actions, "speech_response": "Snapped window to right half."}

        if "center_window" in cleaned or "center" in cleaned or "dua vao giua" in cleaned or "giua man hinh" in cleaned:
            actions.append({"tool": "snap_window", "params": {"position": "center"}})
            return {"actions": actions, "speech_response": "Centered window on screen."}

        # 3b. Window Minimization & Maximization
        if "minimize_window" in cleaned or "minimize" in cleaned or "thu nhỏ" in cleaned or "thu nho" in cleaned or "hạ cửa sổ" in cleaned or "ha cua so" in cleaned:
            actions.append({"tool": "minimize_window", "params": {}})
            return {"actions": actions, "speech_response": "Minimized window."}

        if "maximize_window" in cleaned or "maximize" in cleaned or "phóng to" in cleaned or "phong to" in cleaned or "toàn màn hình" in cleaned or "toan man hinh" in cleaned or "fullscreen" in cleaned:
            actions.append({"tool": "maximize_window", "params": {}})
            return {"actions": actions, "speech_response": "Maximized window."}

        # 3c. Page Scrolling / Rolling (YouTube, Browser, Active Window)
        scroll_down_patterns = (
            "scroll_down", "scroll down", "roll down", "roll_down", "row down", "raw down",
            "cuon xuong", "cuộn xuống", "keo xuong", "kéo xuống", "luot xuong", "lướt xuống",
            "xuong duoi", "xuống dưới", "lan chuot xuong", "lăn chuột xuống", "cuon trang xuong", "cuộn trang xuống"
        )
        scroll_up_patterns = (
            "scroll_up", "scroll up", "roll up", "roll_up", "row up", "raw up",
            "cuon len", "cuộn lên", "keo len", "kéo lên", "luot len", "lướt lên",
            "len tren", "lên trên", "lan chuot len", "lăn chuột lên", "cuon trang len", "cuộn trang lên"
        )
        scroll_top_patterns = (
            "scroll to top", "len dau trang", "lên đầu trang", "dau trang", "đầu trang", "ve dau trang", "về đầu trang"
        )
        scroll_bottom_patterns = (
            "scroll to bottom", "xuong cuoi trang", "xuống cuối trang", "cuoi trang", "cuối trang", "ve cuoi trang", "về cuối trang"
        )

        if any(sp in cleaned for sp in scroll_top_patterns):
            actions.append({"tool": "scroll_page", "params": {"direction": "top"}})
            return {"actions": actions, "speech_response": "Scrolled to top of page."}

        if any(sp in cleaned for sp in scroll_bottom_patterns):
            actions.append({"tool": "scroll_page", "params": {"direction": "bottom"}})
            return {"actions": actions, "speech_response": "Scrolled to bottom of page."}

        if any(sp in cleaned for sp in scroll_down_patterns):
            actions.append({"tool": "scroll_page", "params": {"direction": "down", "amount": 6}})
            return {"actions": actions, "speech_response": "Scrolling down."}

        if any(sp in cleaned for sp in scroll_up_patterns):
            actions.append({"tool": "scroll_page", "params": {"direction": "up", "amount": 6}})
            return {"actions": actions, "speech_response": "Scrolling up."}

        # 4. Window Switching / Focus
        switch_patterns = (
            "switch_window", "switch window", "switch to", "next window", "other window",
            "doi cua so", "chuyen cua so", "chuyen window", "doi window",
            "đổi cửa sổ", "chuyển cửa sổ", "chuyển window", "đổi window",
            "chuyển qua", "chuyển sang", "chuyen qua", "chuyen sang", "alt tab",
            "cửa sổ khác", "cua so khac", "cửa sổ hiện tại", "cua so hien tai",
            "chuyển", "chuyen", "đổi", "doi"
        )
        has_window_kw = any(w in cleaned for w in ("cửa sổ", "cua so", "window", "trình duyệt", "browser", "chrome", "vscode", "code", "spotify", "youtube"))
        if ctx.intent == "FOCUS_APPLICATION" or (any(sp in cleaned for sp in switch_patterns) and has_window_kw):
            target_app = ctx.target_entity.name if ctx.target_entity else None
            if not target_app:
                for app_name in ("chrome", "browser", "trình duyệt", "trinh duyet", "vscode", "code", "antigravity", "cursor", "spotify", "discord", "notepad", "youtube"):
                    if app_name in cleaned:
                        target_app = "chrome" if app_name in ("browser", "trình duyệt", "trinh duyet") else app_name
                        break

            actions.append({
                "tool": "switch_window",
                "params": {"app_name": target_app}
            })
            speech = f"Switching to {target_app}." if target_app else "Switching window."
            return {"actions": actions, "speech_response": speech}

        # 5. Window Closing
        close_patterns = (
            "close_window", "close window", "closed window", "close windows",
            "close youtube", "close chrome", "close browser", "close tab", "close app",
            "dong cua so", "tat cua so", "đóng cửa sổ", "tắt cửa sổ", "dong tab", "tat tab",
            "quit window", "dong lai", "tat app"
        )
        if any(cp in cleaned for cp in close_patterns) or ctx.intent == "CLOSE_APPLICATION":
            target_app = ctx.target_entity.name if ctx.target_entity else None
            if not target_app:
                for app_name in ("chrome", "vscode", "code", "antigravity", "cursor", "spotify", "discord", "notepad", "youtube", "browser"):
                    if app_name in cleaned:
                        target_app = "chrome" if app_name in ("youtube", "browser") else app_name
                        break

            actions.append({
                "tool": "close_window",
                "params": {"app_name": target_app}
            })
            speech = f"Closing {target_app}." if target_app else "Closing window."
            return {"actions": actions, "speech_response": speech}

        # 6. Search in Google / YouTube / Browser (English & Vietnamese)
        search_patterns = [
            r"(?:mở|bật)\s+(?:browser|chrome|trình\s+duyệt|youtube)\s+(?:và\s+)?(?:tìm(?:\s+(?:kiếm|cho\s+tôi|về))?|search(?:\s+(?:cho|for|on|about))?|tra\s+cứu)\s+(.+)",
            r"(?:tìm(?:\s+(?:kiếm|cho\s+tôi|về))?|tra\s+cứu)\s+(.+)",
            r"(?:open\s+(?:browser|chrome|youtube)\s+(?:and\s+)?)?(?:search(?:\s+(?:for|on|about))?|look\s+up|\bgoogle\s+(?!chrome\b))\s+(.+)",
            r"(?:search(?:\s+(?:for|on|about))?|look\s+up|\bgoogle\s+(?!chrome\b))\s+(.+)",
            r"(?:gõ|nhập|type)\s+(?:vào\s+(?:thanh\s+tìm\s+kiếm|search|thanh\s+địa\s+chỉ)\s+)?(.+)",
        ]

        query = None
        is_youtube = "youtube" in cleaned

        for pat in search_patterns:
            m = re.search(pat, cleaned)
            if m:
                query = m.group(1).strip()
                break

        if query:
            video_idx = None
            if re.search(r"(?:và\s+)?(?:chọn|click|play|select)\s+(?:video\s+)?(?:thứ\s+2|thứ\s+hai|2|second|2nd)", query):
                video_idx = 2
                query = re.sub(r"\s+(?:và\s+)?(?:chọn|click|play|select)\s+(?:video\s+)?(?:thứ\s+2|thứ\s+hai|2|second|2nd).*", "", query).strip()
            elif re.search(r"(?:và\s+)?(?:chọn|click|play|select)\s+(?:video\s+)?(?:thứ\s+1|thứ\s+nhất|đầu\s+tiên|1|first|1st)", query):
                video_idx = 1
                query = re.sub(r"\s+(?:và\s+)?(?:chọn|click|play|select)\s+(?:video\s+)?(?:thứ\s+1|thứ\s+nhất|đầu\s+tiên|1|first|1st).*", "", query).strip()
            elif re.search(r"(?:và\s+)?(?:chọn|click|play|select)\s+(?:video\s+)?(?:thứ\s+3|thứ\s+ba|3|third|3rd)", query):
                video_idx = 3
                query = re.sub(r"\s+(?:và\s+)?(?:chọn|click|play|select)\s+(?:video\s+)?(?:thứ\s+3|thứ\s+ba|3|third|3rd).*", "", query).strip()

            query = re.sub(r"\s+(?:in\s+(?:chrome|browser|google|youtube)|trên\s+(?:google|youtube|mạng)|cho\s+tôi)$", "", query).strip()
            explicit_open = any(k in cleaned for k in ("mở", "mo", "bật", "bat", "open", "launch"))

            ctx_win = ComputerUseTool.get_active_window_context()
            if not explicit_open and (ctx_win.get("is_browser") or ctx_win.get("is_youtube")):
                actions.append({
                    "tool": "search_in_active_window",
                    "params": {"query": query}
                })
                if video_idx is not None:
                    actions.append({
                        "tool": "select_youtube_video",
                        "params": {"index": video_idx}
                    })
                    speech = f"Searching for {query} and selecting video {video_idx}."
                else:
                    speech = f"Searching for {query} in current window."
                return {"actions": actions, "speech_response": speech}

            engine = "youtube" if is_youtube else "google"
            actions.append({
                "tool": "search_web",
                "params": {"query": query, "engine": engine}
            })
            if video_idx is not None and is_youtube:
                actions.append({
                    "tool": "select_youtube_video",
                    "params": {"index": video_idx}
                })
                speech = f"Searching YouTube for {query} and selecting video {video_idx}."
            else:
                speech = f"Searching YouTube for {query}, sir." if is_youtube else f"Opening browser and searching for {query}."
            return {"actions": actions, "speech_response": speech}

        # 7. Minimize / Maximize Window
        if "minimize_window" in cleaned or "minimize" in cleaned or "minimise" in cleaned or "thu nho" in cleaned or "an cua so" in cleaned or "many my" in cleaned or "many mice" in cleaned:
            actions.append({"tool": "minimize_window", "params": {}})
            return {"actions": actions, "speech_response": "Window minimized."}

        if "maximize_window" in cleaned or "maximize" in cleaned or "phong to" in cleaned or "toan man hinh" in cleaned or "fullscreen" in cleaned:
            actions.append({"tool": "maximize_window", "params": {}})
            return {"actions": actions, "speech_response": "Window maximized."}

        # 8. Open YouTube + Video Selection (Compound Intent)
        if "youtube" in cleaned and any(k in cleaned for k in ("video", "thu 1", "thu 2", "first", "second", "chọn", "select", "play")):
            video_idx = 2 if any(k in cleaned for k in ("thu 2", "thu hai", "thứ hai", "2", "second", "2nd")) else 1
            if any(k in cleaned for k in ("thu 3", "thu ba", "thứ ba", "3", "third", "3rd")):
                video_idx = 3
            actions.append({"tool": "open_url", "params": {"url": "https://www.youtube.com"}})
            actions.append({"tool": "select_youtube_video", "params": {"index": video_idx}})
            return {"actions": actions, "speech_response": f"Opening YouTube and selecting video {video_idx}."}

        # 8b. Active Window YouTube Video Selection / Click
        video_select_match = re.search(
            r"(?:chọn|click|play|bật|mở|select|xem|phát)?\s*(?:video|clip)?\s*(?:thứ\s*|number\s*|so\s*|số\s*)?(\d+|dau\s*tien|đầu\s*tiên|first|1st|one|một|thu\s*hai|thứ\s*hai|second|2nd|two|hai|thu\s*ba|thứ\s*ba|third|3rd|three|ba|thu\s*bon|thứ\s*bốn|thứ\s*tư|thu\s*tu|thứ\s*tự|thứ\s*ư|thức\s*ư|fourth|4th|four|for|fall|far|bốn|tư|thu\s*nam|thứ\s*năm|fifth|5th|five|năm|thu\s*sau|thứ\s*sáu|sixth|6th|six|sáu|thu\s*bay|thứ\s*bảy|seventh|7th|seven|bảy|thu\s*tam|thứ\s*tám|eighth|8th|eight|tám|thu\s*chin|thứ\s*chín|ninth|9th|nine|chín|mười|ten|10th|tiếp\s*theo|tiếp\s*tục|next)",
            cleaned
        )
        if (video_select_match and any(vk in cleaned for vk in ("video", "clip", "chọn", "select", "play", "thứ", "thu"))) or any(k in cleaned for k in ("second video", "first video", "third video", "fourth video", "fifth video", "video 1", "video 2", "video 3", "video 4", "video 5", "video 6")):
            idx = 1
            if video_select_match:
                raw_idx = video_select_match.group(1).strip().lower()
                if raw_idx in ("2", "thu hai", "thứ hai", "second", "2nd", "two", "hai"):
                    idx = 2
                elif raw_idx in ("3", "thu ba", "thứ ba", "third", "3rd", "three", "ba"):
                    idx = 3
                elif raw_idx in ("4", "thu bon", "thứ bốn", "thứ tư", "thu tu", "thứ tự", "thứ ư", "thức ư", "fourth", "4th", "four", "for", "fall", "far", "bốn", "tư"):
                    idx = 4
                elif raw_idx in ("5", "thu nam", "thứ năm", "fifth", "5th", "five", "năm"):
                    idx = 5
                elif raw_idx in ("6", "thu sau", "thứ sáu", "sixth", "6th", "six", "sáu"):
                    idx = 6
                elif raw_idx in ("7", "thu bay", "thứ bảy", "seventh", "7th", "seven", "bảy"):
                    idx = 7
                elif raw_idx in ("8", "thu tam", "thứ tám", "eighth", "8th", "eight", "tám"):
                    idx = 8
                elif raw_idx in ("9", "thu chin", "thứ chín", "ninth", "9th", "nine", "chín"):
                    idx = 9
                elif raw_idx in ("10", "mười", "ten", "10th"):
                    idx = 10
                elif raw_idx in ("tiếp theo", "tiếp tục", "next"):
                    idx = 1
                elif raw_idx.isdigit():
                    idx = int(raw_idx)
            elif "second" in cleaned or "2" in cleaned or "thu 2" in cleaned:
                idx = 2
            elif "third" in cleaned or "3" in cleaned or "thu 3" in cleaned:
                idx = 3
            elif "fourth" in cleaned or "4" in cleaned or "thu 4" in cleaned or "for" in cleaned or "thứ tự" in cleaned or "thứ ư" in cleaned:
                idx = 4
            elif "fifth" in cleaned or "5" in cleaned or "thu 5" in cleaned:
                idx = 5

            actions.append({"tool": "select_youtube_video", "params": {"index": idx}})
            return {"actions": actions, "speech_response": f"Playing video {idx}."}

        # 9. Open URL / Website
        url_match = re.search(r"(?:open|go\s+to|vào\s+trang)\s+(https?://\S+|www\.\S+|\S+\.(?:com|org|net|io|ai|vn))", cleaned)
        if url_match:
            raw_url = url_match.group(1).strip()
            actions.append({"tool": "open_url", "params": {"url": raw_url}})
            return {"actions": actions, "speech_response": f"Navigating to {raw_url}."}

        # 10. File Discovery
        if "find" in cleaned or "latest" in cleaned or "download" in cleaned or "tìm file" in cleaned or "tệp" in cleaned:
            ext = None
            if "pdf" in cleaned:
                ext = "pdf"
            elif "image" in cleaned or "photo" in cleaned or "png" in cleaned or "jpg" in cleaned:
                ext = "png"
            elif "zip" in cleaned:
                ext = "zip"

            folder = "Downloads"
            if "document" in cleaned:
                folder = "Documents"
            elif "desktop" in cleaned:
                folder = "Desktop"

            actions.append({
                "tool": "find_latest_file",
                "params": {"folder": folder, "extension": ext}
            })
            return {"actions": actions, "speech_response": f"Checking for the latest {ext or 'file'} in {folder}."}

        # 11. System Health / Telemetry
        if "system" in cleaned or "status" in cleaned or "cpu" in cleaned or "ram" in cleaned or "battery" in cleaned or "hệ thống" in cleaned:
            actions.append({"tool": "get_system_status", "params": {}})
            return {"actions": actions, "speech_response": "System metrics retrieved. Performance is nominal."}

        # 11b. Direct Browser / IDE / YouTube Opening Rules
        if any(b in cleaned for b in ("youtube", "you tube", "u tube", "du tup", "du túp", "diu tup", "diu túp")) and any(k in cleaned for k in ("mở", "bật", "open", "launch", "start", "vào", "vao")):
            actions.append({"tool": "open_url", "params": {"url": "https://www.youtube.com"}})
            return {"actions": actions, "speech_response": "Opening YouTube."}

        if any(b in cleaned for b in ("trình duyệt", "browser", "chrome", "google chrome", "web browser")) and any(k in cleaned for k in ("mở", "bật", "open", "launch", "start")):
            actions.append({"tool": "open_application", "params": {"app_name": "Google Chrome"}})
            return {"actions": actions, "speech_response": "Opening Google Chrome."}

        if any(b in cleaned for b in ("vs code", "vscode", "visual studio code", "code editor")) and any(k in cleaned for k in ("mở", "bật", "open", "launch", "start")):
            actions.append({"tool": "open_application", "params": {"app_name": "Visual Studio Code"}})
            return {"actions": actions, "speech_response": "Opening Visual Studio Code."}

        # 12. Application Launch via Resolved Entity
        if ctx.target_entity and ctx.target_entity.confidence >= 0.75 and (ctx.intent == "OPEN_APPLICATION" or any(k in cleaned for k in ("open", "mở", "bật", "launch"))):
            app_display_name = ctx.target_entity.name
            actions.append({
                "tool": "open_application",
                "params": {"app_name": app_display_name}
            })
            return {"actions": actions, "speech_response": f"Opening {app_display_name}."}

        # 13. Wake & Presence Acknowledgment in Conversation Mode
        wake_greetings = {
            "jarvis", "javis", "javas", "hey jarvis", "jarvis ơi", "ơi jarvis",
            "jarvis đâu rồi", "jarvis nghe không", "nghe không jarvis", "are you there",
            "can you hear me", "jarvis listening"
        }
        cleaned_words = re.sub(r'[^\w\s]', '', cleaned).strip()
        if cleaned_words in wake_greetings or any(cleaned_words == wg for wg in wake_greetings):
            return {
                "actions": [],
                "speech_response": "Yes, I am here and listening. How can I help you?"
            }

        conversational_greetings = ("hello", "hi", "who are you", "what can you do", "help me", "how are you", "what are you", "bạn là ai", "giúp tôi", "chào bạn")
        if any(cg in cleaned for cg in conversational_greetings):
            return {
                "actions": [],
                "speech_response": "I am Jarvis, your desktop AI assistant. I can open applications, switch or close windows, search the web, inspect files, and manage your workspace."
            }

        # 14. Non-actionable utterance -> Silent recovery (no TTS voice spam)
        log.info("[HERMES_RUNTIME] Non-actionable utterance '%s' -> Silent recovery", cleaned)
        return {
            "actions": [],
            "speech_response": ""
        }

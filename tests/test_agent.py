"""
Unit tests for Hermes Agent Client, Tools, and Safety Policy.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.agent_events import AgentEvent, EventType
from agent.command_router import CommandRouter, RouteTarget
from agent.hermes_client import HermesClient
from agent.safety_policy import SafetyPolicy


from agent.voice_memory import VoiceMemory
from agent.hermes_runtime import HermesRuntime
from agent.tools.computer_use import ComputerUseTool


def test_command_router():
    # Deterministic commands
    target, action, meta = CommandRouter.route("open spotify")
    assert target == RouteTarget.DETERMINISTIC_ACTION
    assert action == "open_spotify"

    target, action, meta = CommandRouter.route("open vs code")
    assert target == RouteTarget.DETERMINISTIC_ACTION
    assert action == "open_vscode"

    # Sleep command (closes Jarvis session)
    target, action, meta = CommandRouter.route("jarvis go to sleep")
    assert target == RouteTarget.SLEEP_DISMISS

    # Window closing commands (must route to Hermes to close desktop windows, NOT Jarvis)
    target, action, meta = CommandRouter.route("close window")
    assert target == RouteTarget.HERMES_AGENT

    target, action, meta = CommandRouter.route("dong cua so")
    assert target == RouteTarget.HERMES_AGENT

    # Natural-language task for Hermes
    target, action, meta = CommandRouter.route("open chrome and search for blender tutorials")
    assert target == RouteTarget.HERMES_AGENT
    assert action == "agent_task"


def test_voice_memory_and_learning():
    vm = VoiceMemory.get_instance()

    # 1. Phonetic Guessing
    norm, corrected = vm.normalize("orban browsers")
    assert norm == "open chrome"
    assert corrected is True

    norm, corrected = vm.normalize("les second videos")
    assert norm == "click second video"
    assert corrected is True

    # 2. Dynamic Learning
    vm.learn("mo trinh duyet", "open chrome")
    norm, corrected = vm.normalize("mo trinh duyet")
    assert norm == "open chrome"


def test_search_and_window_intents():
    runtime = HermesRuntime()

    # 1. Vietnamese Search Intent ("mở browser và tìm cho tôi blender tutorials")
    plan1 = runtime._plan_instruction("mở browser và tìm cho tôi blender tutorials")
    assert len(plan1["actions"]) > 0
    assert plan1["actions"][0]["tool"] == "search_web"
    assert "blender tutorials" in plan1["actions"][0]["params"]["query"]

    # 2. English Search Intent ("open browser and search for lofi music")
    plan2 = runtime._plan_instruction("open browser and search for lofi music")
    assert len(plan2["actions"]) > 0
    assert plan2["actions"][0]["tool"] == "search_web"
    assert "lofi music" in plan2["actions"][0]["params"]["query"]

    # 3. Window Switching Intent
    plan3 = runtime._plan_instruction("switch window")
    assert len(plan3["actions"]) > 0
    assert plan3["actions"][0]["tool"] == "switch_window"

    plan3_app = runtime._plan_instruction("switch to chrome")
    assert plan3_app["actions"][0]["tool"] == "switch_window"
    assert "chrome" in plan3_app["actions"][0]["params"]["app_name"].lower()

    # 4. Window Closing Intent (English & Vietnamese phonetic variations)
    plan4 = runtime._plan_instruction("close window")
    assert len(plan4["actions"]) > 0
    assert plan4["actions"][0]["tool"] == "close_window"

    plan4_vn = runtime._plan_instruction("đóng cửa sổ")
    assert len(plan4_vn["actions"]) > 0
    assert plan4_vn["actions"][0]["tool"] == "close_window"

    # 5. YouTube Video Selection Intent
    plan5 = runtime._plan_instruction("click second video")
    assert len(plan5["actions"]) > 0
    assert plan5["actions"][0]["tool"] == "select_youtube_video"
    assert plan5["actions"][0]["params"]["index"] == 2

    # 6. Compound Intent: YouTube Search + Select Video
    # "mở youtube search bài nhạc chill và chọn video đầu tiên"
    plan6 = runtime._plan_instruction("mở youtube search bài nhạc chill và chọn video đầu tiên")
    assert len(plan6["actions"]) == 2
    assert plan6["actions"][0]["tool"] == "search_web"
    assert "bài nhạc chill" in plan6["actions"][0]["params"]["query"]
    assert plan6["actions"][1]["tool"] == "select_youtube_video"
    assert plan6["actions"][1]["params"]["index"] == 1

    # 7. Compound Intent: Open YouTube + Select Video
    # "mở youtube chọn video thứ 2"
    plan7 = runtime._plan_instruction("mở youtube chọn video thứ 2")
    assert len(plan7["actions"]) == 2
    assert plan7["actions"][0]["tool"] == "open_url"
    assert plan7["actions"][1]["tool"] == "select_youtube_video"
    assert plan7["actions"][1]["params"]["index"] == 2

    # 8. Accented Search Intent ("open browser and snap yeah see the right" -> search chatgpt)
    plan8 = runtime._plan_instruction("open browser and snap yeah see the right")
    assert len(plan8["actions"]) > 0
    assert plan8["actions"][0]["tool"] == "search_web"
    assert "chatgpt" in plan8["actions"][0]["params"]["query"]

    # 9. Accented YouTube Open & Select ("orban youtube and select")
    plan9 = runtime._plan_instruction("orban youtube and select")
    assert len(plan9["actions"]) == 2
    assert plan9["actions"][0]["tool"] == "open_url"
    assert plan9["actions"][1]["tool"] == "select_youtube_video"

    # 10. Direct Play Video Intent ("play video 1", "bật video 1")
    plan10 = runtime._plan_instruction("play video 1")
    assert len(plan10["actions"]) > 0
    assert plan10["actions"][0]["tool"] == "select_youtube_video"
    assert plan10["actions"][0]["params"]["index"] == 1

    # 11. Accented Window Close Intent ("klaus that youtube window", "klaus cool read window")
    plan11 = runtime._plan_instruction("klaus that youtube window")
    assert len(plan11["actions"]) > 0
    assert plan11["actions"][0]["tool"] == "close_window"

    plan12 = runtime._plan_instruction("klaus cool read window")
    assert len(plan12["actions"]) > 0
    assert plan12["actions"][0]["tool"] == "close_window"

    # 12. Active Window Context Inspection
    ctx = ComputerUseTool.get_active_window_context()
    assert "app" in ctx
    assert "title" in ctx
    assert "is_browser" in ctx
    assert "is_youtube" in ctx
    assert "is_vscode" in ctx

    # 13. Window Snapping & Grid Layout Intent
    plan13 = runtime._plan_instruction("top right")
    assert len(plan13["actions"]) > 0
    assert plan13["actions"][0]["tool"] == "snap_window"
    assert plan13["actions"][0]["params"]["position"] == "top_right"

    plan14 = runtime._plan_instruction("keo sang trai")
    assert len(plan14["actions"]) > 0
    assert plan14["actions"][0]["tool"] == "snap_window"
    assert plan14["actions"][0]["params"]["position"] == "left"

    # 14. Tab Management & Navigation Intent
    plan15 = runtime._plan_instruction("next tab")
    assert len(plan15["actions"]) > 0
    assert plan15["actions"][0]["tool"] == "manage_tab"
    assert plan15["actions"][0]["params"]["action"] == "next"

    plan16 = runtime._plan_instruction("chon tab 2")
    assert len(plan16["actions"]) > 0
    assert plan16["actions"][0]["tool"] == "manage_tab"
    assert plan16["actions"][0]["params"]["action"] == "select"
    assert plan16["actions"][0]["params"]["index"] == 2


def test_safety_policy():
    allowed, reason = SafetyPolicy.evaluate_action("open_application", {"app_name": "chrome"})
    assert allowed is True

    allowed, reason = SafetyPolicy.evaluate_action("run_powershell", {"command": "del /f /s /q C:\\Windows"})
    assert allowed is False
    assert "blocked" in reason.lower()


def test_hermes_client_workflow():
    client = HermesClient()
    events_received = []

    def on_event(evt: AgentEvent):
        events_received.append(evt.event_type)

    async def _run():
        session_id = "test-session-123"
        assert await client.start_session(session_id) is True

        response = await client.send_message(
            session_id=session_id,
            message="Open Chrome and search for Blender tutorials",
            event_callback=on_event,
        )

        assert response.success is True
        assert "blender" in response.text.lower() or "chrome" in response.text.lower() or "browser" in response.text.lower()
        assert len(response.tools_executed) > 0
        assert response.tools_executed[0]["tool"] == "search_web"

        # Verify event stream
        assert EventType.AGENT_STARTED in events_received
        assert EventType.AGENT_THINKING in events_received
        assert EventType.AGENT_TOOL_STARTED in events_received
        assert EventType.AGENT_TOOL_FINISHED in events_received
        assert EventType.AGENT_COMPLETED in events_received

        await client.close_session(session_id)

    asyncio.run(_run())


if __name__ == "__main__":
    test_command_router()
    test_voice_memory_and_learning()
    test_search_and_window_intents()
    test_safety_policy()
    test_hermes_client_workflow()
    print("All Hermes Agent unit tests passed successfully!")

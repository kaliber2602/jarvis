"""
HermesClient: Adapter connecting Jarvis Chat Mode to the Hermes Agent Runtime.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable

from .agent_events import AgentEvent, EventType
from .base_client import AgentClient, AgentResponse
from .hermes_runtime import HermesRuntime

log = logging.getLogger("hermes_client")


class HermesClient(AgentClient):
    """
    Adapter implementing the AgentClient interface for Hermes Agent.
    Hides runtime details (in-process, subprocess, HTTP, IPC) from Jarvis.
    """

    def __init__(self):
        self.host = os.environ.get("HERMES_HOST", "127.0.0.1")
        self.port = int(os.environ.get("HERMES_PORT", "8000"))
        self.timeout_s = float(os.environ.get("HERMES_TIMEOUT", "30.0"))
        self.enabled = os.environ.get("HERMES_ENABLED", "True").strip().lower() in ("true", "1", "yes")

        # Local Runtime instance
        self._runtime = HermesRuntime()

    async def is_available(self) -> bool:
        """Check if Hermes runtime is operational."""
        return self.enabled

    async def start_session(self, session_id: str) -> bool:
        """Initialize session in Hermes runtime."""
        if not self.enabled:
            log.warning("[HERMES_CLIENT] Hermes is disabled in configuration.")
            return False
        return self._runtime.start_session(session_id)

    async def send_message(
        self,
        session_id: str,
        message: str,
        event_callback: Callable[[AgentEvent], None] | None = None,
        interpretation_context: Any = None,
    ) -> AgentResponse:
        """
        Send user message to Hermes runtime and await planned response.
        Streams intermediate progress events to event_callback.
        """
        if not self.enabled:
            log.warning("[HERMES_CLIENT] Hermes is disabled. Returning fallback message.")
            return AgentResponse(
                session_id=session_id,
                text="The agent service is currently disabled, sir.",
                success=False,
                error="HERMES_DISABLED",
            )

        log.info("[HERMES_CLIENT] Sending message to Hermes for session %s: '%s'", session_id, message)

        try:
            # Wrap execution in timeout
            response = await asyncio.wait_for(
                self._runtime.run_plan(
                    session_id=session_id,
                    instruction=message,
                    event_cb=event_callback,
                    interpretation_context=interpretation_context,
                ),
                timeout=self.timeout_s,
            )
            log.info("[HERMES_CLIENT] Received Hermes response: '%s'", response.text)
            return response
        except asyncio.TimeoutError:
            log.error("[HERMES_CLIENT] Timeout waiting for Hermes response (%.1fs)", self.timeout_s)
            if event_callback:
                event_callback(AgentEvent(
                    session_id=session_id,
                    event_type=EventType.AGENT_ERROR,
                    payload={"error": "Operation timed out."}
                ))
            return AgentResponse(
                session_id=session_id,
                text="The operation timed out, sir. Please try again.",
                success=False,
                error="TIMEOUT",
            )
        except Exception as e:
            log.error("[HERMES_CLIENT] Error during Hermes execution: %s", e, exc_info=True)
            if event_callback:
                event_callback(AgentEvent(
                    session_id=session_id,
                    event_type=EventType.AGENT_ERROR,
                    payload={"error": str(e)}
                ))
            return AgentResponse(
                session_id=session_id,
                text="I encountered an issue executing that command, sir.",
                success=False,
                error=str(e),
            )

    async def cancel_session(self, session_id: str) -> None:
        """Cancel ongoing session."""
        self._runtime.cancel_session(session_id)

    async def close_session(self, session_id: str) -> None:
        """Close session."""
        self._runtime.close_session(session_id)

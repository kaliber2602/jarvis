"""
Abstract AgentClient interface for Jarvis mode integration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable
from .agent_events import AgentEvent


@dataclass
class AgentResponse:
    """Final output response from the agent session."""
    session_id: str
    text: str
    success: bool = True
    error: str | None = None
    tools_executed: list[dict[str, Any]] = field(default_factory=list)


class AgentClient(ABC):
    """Abstract interface for communicating with an external Agent Runtime."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the Agent Runtime is reachable and ready."""
        pass

    @abstractmethod
    async def start_session(self, session_id: str) -> bool:
        """Initialize an agent session for a given conversation session ID."""
        pass

    @abstractmethod
    async def send_message(
        self,
        session_id: str,
        message: str,
        event_callback: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResponse:
        """
        Send a user utterance/instruction to the agent runtime.
        Streams intermediate lifecycle events to event_callback and returns the final AgentResponse.
        """
        pass

    @abstractmethod
    async def cancel_session(self, session_id: str) -> None:
        """Cancel ongoing execution for the specified session."""
        pass

    @abstractmethod
    async def close_session(self, session_id: str) -> None:
        """Gracefully terminate the agent session and release resources."""
        pass

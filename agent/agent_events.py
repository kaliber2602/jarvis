"""
Agent lifecycle and progress event definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class EventType(str, Enum):
    """Types of agent progress and status events."""
    AGENT_STARTED = "agent.started"
    AGENT_THINKING = "agent.thinking"
    AGENT_TOOL_STARTED = "agent.tool.started"
    AGENT_TOOL_PROGRESS = "agent.tool.progress"
    AGENT_TOOL_FINISHED = "agent.tool.finished"
    AGENT_VERIFYING = "agent.verifying"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"


@dataclass
class AgentEvent:
    """Represents a discrete agent lifecycle or execution event."""
    session_id: str
    event_type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "type": self.event_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }

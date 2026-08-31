"""
Interaction Models & Standardized Data Types for Hermes Interaction Engine.
Defines UIComponent, ComponentSource, UIActionType, ErrorCode, and Exactly-Once Action Contracts.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class ComponentSource(str, Enum):
    """Origin source for UI component discovery and interaction capability."""
    DOM = "DOM"
    UIA = "UIA"
    CV = "CV"


class UIActionType(str, Enum):
    """Atomic interaction actions supported by InteractionController."""
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    HOVER = "HOVER"
    FOCUS = "FOCUS"
    TYPE = "TYPE"
    SELECT = "SELECT"


class ExecutionMethod(str, Enum):
    """Concrete execution method used to perform an action."""
    DOM_CLICK = "DOM_CLICK"
    UIA_INVOKE = "UIA_INVOKE"
    MOUSE_CLICK = "MOUSE_CLICK"


class ErrorCode(str, Enum):
    """Standardized error codes for target resolution, window/process state, and interaction."""
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    TARGET_LOW_CONFIDENCE = "TARGET_LOW_CONFIDENCE"
    WINDOW_NOT_FOUND = "WINDOW_NOT_FOUND"
    WINDOW_NOT_FOREGROUND = "WINDOW_NOT_FOREGROUND"
    PROCESS_NOT_RUNNING = "PROCESS_NOT_RUNNING"
    MOUSE_MOVE_FAILED = "MOUSE_MOVE_FAILED"
    ACTION_FAILED = "ACTION_FAILED"
    ACTION_VERIFICATION_FAILED = "ACTION_VERIFICATION_FAILED"
    ACTION_ALREADY_EXECUTED = "ACTION_ALREADY_EXECUTED"


@dataclass
class UIComponent:
    """
    Standardized abstraction for any interactable UI element or component.
    Supports DOM elements, native Windows UI Automation controls, and Computer Vision bounding boxes.
    """
    id: str
    type: str = "component"
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # (x, y, width, height)
    center: tuple[float, float] = (0.0, 0.0)
    row: int = -1
    column: int = -1
    confidence: float = 1.0
    source: ComponentSource = ComponentSource.CV
    native_handle: int = 0
    dom_reference: Optional[Any] = None
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.center == (0.0, 0.0) and self.bbox != (0.0, 0.0, 0.0, 0.0):
            x, y, w, h = self.bbox
            self.center = (x + w / 2.0, y + h / 2.0)

    @property
    def left(self) -> float:
        return self.bbox[0]

    @property
    def top(self) -> float:
        return self.bbox[1]

    @property
    def width(self) -> float:
        return self.bbox[2]

    @property
    def height(self) -> float:
        return self.bbox[3]

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def center_x(self) -> float:
        return self.center[0]

    @property
    def center_y(self) -> float:
        return self.center[1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "bbox": {"x": self.left, "y": self.top, "width": self.width, "height": self.height},
            "center": {"x": self.center_x, "y": self.center_y},
            "row": self.row,
            "column": self.column,
            "confidence": round(self.confidence, 3),
            "source": self.source.value,
            "text": self.text,
            "native_handle": self.native_handle,
            "has_dom_ref": self.dom_reference is not None,
        }


@dataclass
class ActionExecution:
    """
    Atomic Action Execution Contract enforcing the EXACTLY-ONCE ACTION POLICY.
    Invariant: execution_count <= 1.
    """
    action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_type: UIActionType = UIActionType.CLICK
    target_component: Optional[UIComponent] = None
    execution_count: int = 0
    executed_method: Optional[ExecutionMethod] = None
    created_at: float = field(default_factory=time.time)
    executed_at: Optional[float] = None

    def mark_executed(self, method: ExecutionMethod) -> None:
        """Mark this atomic action as executed. Fails if already executed."""
        if self.execution_count >= 1:
            raise RuntimeError(f"Action '{self.action_id}' already executed (execution_count={self.execution_count})")
        self.execution_count += 1
        self.executed_method = method
        self.executed_at = time.time()


@dataclass
class ActionResult:
    """Outcome of an interaction executed by InteractionController."""
    success: bool
    action_id: str
    execution_count: int
    execution_method: Optional[ExecutionMethod] = None
    target_id: str = ""
    source: ComponentSource = ComponentSource.CV
    verification_passed: bool = False
    error_code: Optional[ErrorCode] = None
    error_message: str = ""
    telemetry: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action_id": self.action_id,
            "execution_count": self.execution_count,
            "execution_method": self.execution_method.value if self.execution_method else None,
            "target_id": self.target_id,
            "source": self.source.value,
            "verification_passed": self.verification_passed,
            "error_code": self.error_code.value if self.error_code else None,
            "error_message": self.error_message,
            "telemetry": self.telemetry,
        }

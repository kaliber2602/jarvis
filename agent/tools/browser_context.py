"""
BrowserContext & Window Snapshot models for UI Computer-Use Transactions.
Scoped strictly per transaction (resolve -> snapshot -> interact -> observe -> dispose).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class WindowHandle:
    """
    Immutable identifier for an OS window.
    """
    hwnd: int
    pid: int
    process_name: str
    title: str
    class_name: str


@dataclass(frozen=True)
class WindowSnapshot:
    """
    Immutable point-in-time snapshot of window geometry, client area, and DPI state.
    """
    handle: WindowHandle
    window_rect: tuple[int, int, int, int]       # (left, top, right, bottom)
    client_rect: tuple[int, int, int, int]       # (0, 0, client_width, client_height)
    client_screen_origin: tuple[int, int]        # (screen_x, screen_y)
    client_size: tuple[int, int]                 # (width, height)
    viewport_screen_origin: tuple[int, int]      # (screen_x, screen_y)
    viewport_size: tuple[int, int]               # (width, height)
    browser_chrome_height: int
    dpi: int
    dpi_scale: float
    is_foreground: bool
    is_visible: bool
    is_minimized: bool
    is_maximized: bool

    @property
    def hwnd(self) -> int:
        return self.handle.hwnd

    @property
    def pid(self) -> int:
        return self.handle.pid

    @property
    def title(self) -> str:
        return self.handle.title


@dataclass(frozen=True)
class BrowserContext:
    """
    Transaction-scoped browser session context.
    Disposed after transaction completion.
    """
    window: WindowHandle
    snapshot: WindowSnapshot
    url: str | None = None
    title: str | None = None

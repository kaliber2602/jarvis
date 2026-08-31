"""
Native Windows SendInput and Simulation Backends for Mouse Interaction.
Provides robust, low-level OS mouse querying, cursor setting, and input dispatch
using native Win32 SendInput and virtual desktop metrics.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import logging
import math
import sys
import time
from typing import Optional, Protocol, Tuple

log = logging.getLogger("hermes.mouse_backend")

if sys.platform == "win32":
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    shcore = getattr(ctypes.windll, "shcore", None)

    # Win32 Structures
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", ctypes.c_ulong),
            ("wParamL", ctypes.c_ushort),
            ("wParamH", ctypes.c_ushort),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("u", _INPUT_UNION),
        ]

    INPUT_MOUSE = 0
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_VIRTUALDESK = 0x4000
else:
    user32 = None
    shcore = None
    INPUT = None
    POINT = None
    INPUT_MOUSE = 0
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_VIRTUALDESK = 0x4000


class WindowsSendInputBackend:
    """
    Direct Windows SendInput backend with virtual screen normalization.
    """

    @classmethod
    def get_cursor_position(cls) -> tuple[int, int]:
        if sys.platform != "win32" or not user32 or POINT is None:
            return (0, 0)
        try:
            pt = POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                return (int(pt.x), int(pt.y))
        except Exception as ex:
            log.debug("[MOUSE_BACKEND] GetCursorPos exception: %s", ex)
        return (0, 0)

    @classmethod
    def set_cursor_position(cls, x: int, y: int) -> bool:
        """
        Move cursor using SetCursorPos and SendInput absolute virtual metrics.
        """
        if sys.platform != "win32" or not user32 or INPUT is None:
            return False

        # 1. Hardware cursor placement
        res_set = bool(user32.SetCursorPos(int(x), int(y)))

        # 2. Synchronize via SendInput absolute move
        try:
            v_left = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN = 76
            v_top = user32.GetSystemMetrics(77)    # SM_YVIRTUALSCREEN = 77
            v_width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN = 78
            v_height = user32.GetSystemMetrics(79) # SM_CYVIRTUALSCREEN = 79

            if v_width <= 0:
                v_width = user32.GetSystemMetrics(0) # SM_CXSCREEN = 0
            if v_height <= 0:
                v_height = user32.GetSystemMetrics(1) # SM_CYSCREEN = 1

            v_width = max(1, v_width)
            v_height = max(1, v_height)

            norm_x = int(math.floor(((int(x) - v_left) * 65535.0) / max(1, v_width - 1)))
            norm_y = int(math.floor(((int(y) - v_top) * 65535.0) / max(1, v_height - 1)))

            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.u.mi.dx = norm_x
            inp.u.mi.dy = norm_y
            inp.u.mi.mouseData = 0
            inp.u.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
            inp.u.mi.time = 0
            inp.u.mi.dwExtraInfo = 0

            sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            return res_set or (sent == 1)
        except Exception as ex:
            log.debug("[MOUSE_BACKEND] SendInput move exception: %s", ex)
            return res_set

    @classmethod
    def send_mouse_event(cls, flags: int, data: int = 0, dx: int = 0, dy: int = 0) -> bool:
        if sys.platform != "win32" or not user32 or INPUT is None:
            return False

        try:
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.u.mi.dx = dx
            inp.u.mi.dy = dy
            inp.u.mi.mouseData = data
            inp.u.mi.dwFlags = flags
            inp.u.mi.time = 0
            inp.u.mi.dwExtraInfo = 0

            sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            return sent == 1
        except Exception as ex:
            log.debug("[MOUSE_BACKEND] SendInput event exception: %s", ex)
            return False


class SimulationBackend:
    """
    In-memory simulated backend for testing environments.
    """
    _sim_cursor: tuple[int, int] = (0, 0)
    _move_override: Optional[tuple[int, int]] = None

    @classmethod
    def get_cursor_position(cls) -> tuple[int, int]:
        return cls._sim_cursor

    @classmethod
    def set_cursor_position(cls, x: int, y: int) -> bool:
        if cls._move_override is not None:
            cls._sim_cursor = cls._move_override
        else:
            cls._sim_cursor = (int(x), int(y))
        return True

    @classmethod
    def set_move_override(cls, override_pos: Optional[tuple[int, int]]) -> None:
        cls._move_override = override_pos

    @classmethod
    def send_mouse_event(cls, flags: int, data: int = 0, dx: int = 0, dy: int = 0) -> bool:
        return True

#!/usr/bin/env python3
"""
Jarvis Desktop Window Shell:
Creates a compact, floating, borderless desktop overlay using pywebview (Edge WebView2).
Positioned in the lower-right area of the desktop above the Windows taskbar.
Supports native border resizing and remains hidden until summoned via the wake phrase.
Includes OS-level Named Mutex to guarantee strictly ONE instance running at any time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

import webview
import websockets

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
else:
    user32 = None
    kernel32 = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ui_window")

WS_PORT = int(os.environ.get("JARVIS_WS_PORT", "8765"))
UI_DIR = Path(__file__).resolve().parent / "ui"
INDEX_HTML = UI_DIR / "index.html"

# Default Compact Sizing (Square Floating Widget)
DEFAULT_WIDTH = int(os.environ.get("JARVIS_WINDOW_WIDTH", "480"))
DEFAULT_HEIGHT = int(os.environ.get("JARVIS_WINDOW_HEIGHT", "480"))
MARGIN_RIGHT = 24
MARGIN_BOTTOM = 24

_MUTEX_HANDLE = None


def acquire_single_instance_mutex() -> bool:
    """Acquire Windows Named Mutex to ensure exactly 1 instance of ui_window runs."""
    global _MUTEX_HANDLE
    if sys.platform == "win32" and kernel32 is not None:
        ERROR_ALREADY_EXISTS = 183
        mutex_name = "Global\\JarvisAssistantUI_SingleInstance_Mutex_Lock"
        _MUTEX_HANDLE = kernel32.CreateMutexW(None, True, mutex_name)
        last_error = kernel32.GetLastError()
        if last_error == ERROR_ALREADY_EXISTS:
            log.warning("Another instance of Jarvis Assistant UI is already active. Exiting duplicate instance.")
            return False
    return True


def get_taskbar_safe_position(width: int, height: int) -> tuple[int, int]:
    """Calculate (x, y) coordinates in the lower-right corner of the active work area above the taskbar."""
    if sys.platform == "win32" and user32 is not None:
        try:
            SPI_GETWORKAREA = 0x0030
            rect = wintypes.RECT()
            user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
            work_w = rect.right - rect.left
            work_h = rect.bottom - rect.top

            x = rect.left + max(0, work_w - width - MARGIN_RIGHT)
            y = rect.top + max(0, work_h - height - MARGIN_BOTTOM)
            return x, y
        except Exception as e:
            log.warning("Could not query Windows work area: %s", e)

    return 1200, 500


class JarvisWindowManager:
    """Singleton Window Manager managing the single active Jarvis Orb native window."""

    def __init__(self, window: webview.Window | None = None):
        self.window = window
        self.is_visible = False
        self.running = True
        self.hwnd: int | None = None
        self._lock = threading.Lock()

    def set_window(self, window: webview.Window):
        self.window = window

    def get_hwnd(self) -> int | None:
        if self.hwnd is None and sys.platform == "win32" and user32 is not None:
            self.hwnd = user32.FindWindowW(None, "Jarvis Assistant")
        return self.hwnd

    def is_alive(self) -> bool:
        """Check if native window handle is still valid and not destroyed."""
        if sys.platform == "win32" and user32 is not None:
            hwnd = self.get_hwnd()
            if hwnd:
                return bool(user32.IsWindow(hwnd))
        return self.running

    def show(self):
        with self._lock:
            if self.is_visible:
                return
            self.is_visible = True
            log.info("[UI WINDOW] Showing Jarvis Orb overlay window...")
            try:
                hwnd = self.get_hwnd()
                if hwnd and user32 is not None:
                    SW_SHOWNA = 8
                    HWND_TOPMOST = -1
                    SWP_NOSIZE = 0x0001
                    SWP_NOMOVE = 0x0002
                    SWP_SHOWWINDOW = 0x0040
                    user32.ShowWindowAsync(hwnd, SW_SHOWNA)
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW)
            except Exception as e:
                log.warning("Could not show window: %s", e)

    def hide(self):
        with self._lock:
            if not self.is_visible:
                return
            self.is_visible = False
            log.info("[UI WINDOW] Hiding Jarvis Orb overlay window...")
            try:
                hwnd = self.get_hwnd()
                if hwnd and user32 is not None:
                    SW_HIDE = 0
                    user32.ShowWindowAsync(hwnd, SW_HIDE)
            except Exception as e:
                log.warning("Could not hide window: %s", e)


class WindowJsApi:
    """JS Bridge API enabling native frameless window border drag-resizing."""

    def __init__(self, mgr: JarvisWindowManager):
        self.mgr = mgr

    def start_resize(self, direction_code: int):
        """Initiate native OS window sizing loop on border/corner drag."""
        if sys.platform == "win32" and user32 is not None:
            hwnd = self.mgr.get_hwnd()
            if hwnd:
                WM_SYSCOMMAND = 0x0112
                SC_SIZE = 0xF000
                user32.ReleaseCapture()
                user32.SendMessageW(hwnd, WM_SYSCOMMAND, SC_SIZE + int(direction_code), 0)


def _periodic_ui_memory_trim(mgr: JarvisWindowManager):
    """Periodically release unused WebView2 & CLR working set memory back to the OS."""
    import gc
    if sys.platform == "win32" and kernel32 is not None:
        try:
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            ctypes.windll.psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
            ctypes.windll.psapi.EmptyWorkingSet.restype = wintypes.BOOL
        except Exception:
            pass

    while mgr.running:
        time.sleep(5.0)
        try:
            gc.collect()
            if sys.platform == "win32" and kernel32 is not None:
                ctypes.windll.psapi.EmptyWorkingSet(kernel32.GetCurrentProcess())
        except Exception:
            pass


def start_ws_listener(mgr: JarvisWindowManager):
    """Background asyncio thread to listen for wake/hide signals from Python backend."""
    # Start periodic memory trimming thread
    threading.Thread(target=_periodic_ui_memory_trim, args=(mgr,), daemon=True, name="UIMemoryTrimmer").start()

    async def _listen():
        uri = f"ws://127.0.0.1:{WS_PORT}"
        connected_once = False
        retry_count = 0
        while mgr.running:
            try:
                async with websockets.connect(uri) as ws:
                    log.info("[UI WINDOW] Connected to JarvisBridge at %s", uri)
                    connected_once = True
                    retry_count = 0
                    # Request initial state
                    await ws.send(json.dumps({"type": "get_state"}))

                    async for message in ws:
                        # Fast-skip high-frequency audio telemetry meant for JS renderer
                        if '"audio_level"' in message:
                            continue

                        try:
                            data = json.loads(message)
                            mtype = data.get("type")
                            state = data.get("state")

                            if mtype == "wake_detected":
                                mgr.show()
                            elif mtype in ("session_ended", "ui_hide"):
                                mgr.hide()
                            elif mtype in ("state_changed", "state_sync"):
                                if state in ("hidden", "closing"):
                                    mgr.hide()
                                elif state in ("listening", "processing", "speaking", "agent_thinking", "agent_acting", "agent_verifying", "wake"):
                                    mgr.show()
                        except Exception as ex:
                            log.debug("Error processing message: %s", ex)
            except Exception:
                retry_count += 1
                # If Jarvis backend closed after being connected, exit cleanly
                if connected_once and retry_count >= 3:
                    log.info("[UI WINDOW] Jarvis backend terminated. Exiting UI overlay.")
                    os._exit(0)
                await asyncio.sleep(1.0)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_listen())


def launch_window():
    # Enforce Single-Instance Mutex
    if not acquire_single_instance_mutex():
        sys.exit(0)

    if not INDEX_HTML.is_file():
        log.error("UI file not found: %s", INDEX_HTML)
        sys.exit(1)

    url = INDEX_HTML.as_uri()

    width = DEFAULT_WIDTH
    height = DEFAULT_HEIGHT
    x, y = get_taskbar_safe_position(width, height)

    log.info("Creating compact Jarvis Orb window (%dx%d) at (%d, %d)...", width, height, x, y)

    mgr = JarvisWindowManager()
    api = WindowJsApi(mgr)

    window = webview.create_window(
        title="Jarvis Assistant",
        url=url,
        width=width,
        height=height,
        x=x,
        y=y,
        resizable=True,
        frameless=True,
        easy_drag=False,
        on_top=True,
        js_api=api,
        background_color="#000000",
        hidden=True,  # STRICTLY HIDDEN ON STARTUP!
    )

    mgr.set_window(window)

    # Start WebSocket monitor thread
    listener_thread = threading.Thread(
        target=start_ws_listener,
        args=(mgr,),
        daemon=True,
        name="UIWindowWSListener"
    )
    listener_thread.start()

    log.info("Jarvis desktop UI overlay initialized in hidden background state.")
    webview.start(debug=False)
    mgr.running = False


if __name__ == "__main__":
    launch_window()

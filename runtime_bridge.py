#!/usr/bin/env python3
"""
Jarvis Runtime Bridge: WebSocket communication server and session lifecycle manager.
Bridges the background Python Jarvis runtime coordinator with the Jarvis Orb UI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from typing import Set

import websockets

log = logging.getLogger("jarvis_bridge")

DEFAULT_WS_PORT = int(os.environ.get("JARVIS_WS_PORT", "8765"))
DEFAULT_SESSION_TIMEOUT_S = float(os.environ.get("JARVIS_SESSION_TIMEOUT_S", "45.0"))


class JarvisSession:
    """Represents an active interactive session with Jarvis."""

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.started_at = time.time()
        self.last_activity = time.time()
        self.state = "wake"

    def touch(self) -> None:
        self.last_activity = time.time()

    def is_expired(self, timeout_s: float) -> bool:
        return (time.time() - self.last_activity) > timeout_s


class JarvisBridge:
    """Thread-safe WebSocket event broker for Jarvis UI integration."""

    _instance: JarvisBridge | None = None

    @classmethod
    def get_instance(cls) -> JarvisBridge:
        if cls._instance is None:
            cls._instance = JarvisBridge()
        return cls._instance

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_WS_PORT):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.server_thread: threading.Thread | None = None
        self.running = False

        self.current_state: str = "hidden"
        self.current_session: JarvisSession | None = None
        self.session_timeout_s = DEFAULT_SESSION_TIMEOUT_S

        self._last_audio_broadcast = 0.0
        self._last_tts_broadcast = 0.0
        self._lock = threading.Lock()

        # Session monitor timer
        self._monitor_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the WebSocket server in a background daemon thread."""
        with self._lock:
            if self.running:
                return
            self.running = True

        def _run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._serve())

        self.server_thread = threading.Thread(target=_run, name="JarvisBridgeServer", daemon=True)
        self.server_thread.start()

        # Start session expiration monitor
        self._monitor_thread = threading.Thread(
            target=self._session_expiration_loop,
            name="JarvisSessionMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        log.info("JarvisBridge WebSocket server started on ws://%s:%d", self.host, self.port)

    async def _serve(self):
        for attempt in range(5):
            try:
                async with websockets.serve(self._handle_client, self.host, self.port):
                    while self.running:
                        await asyncio.sleep(0.5)
                break
            except OSError as e:
                if attempt < 4:
                    log.warning("[BRIDGE] Port %d busy (%s). Retrying in 1s (attempt %d/5)...", self.port, e, attempt + 1)
                    await asyncio.sleep(1.0)
                else:
                    log.error("WebSocket server error: %s", e)
            except Exception as e:
                log.error("WebSocket server error: %s", e)
                break

    async def _handle_client(self, websocket):
        self.clients.add(websocket)
        remote = websocket.remote_address
        log.info("[BRIDGE] UI client connected: %s", remote)

        try:
            # Send initial state synchronization
            sync_payload = {
                "type": "state_sync",
                "state": self.current_state,
                "session_active": self.current_session is not None,
                "session_id": self.current_session.session_id if self.current_session else None,
                "timestamp": time.time(),
            }
            await websocket.send(json.dumps(sync_payload))

            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_client_message(websocket, data)
                except json.JSONDecodeError:
                    log.warning("[BRIDGE] Received invalid JSON: %s", message)
        except websockets.exceptions.ConnectionClosed:
            log.info("[BRIDGE] UI client disconnected: %s", remote)
        finally:
            self.clients.discard(websocket)

    async def _handle_client_message(self, websocket, data: dict):
        msg_type = data.get("type")
        if msg_type == "get_state":
            reply = {
                "type": "state_sync",
                "state": self.current_state,
                "session_active": self.current_session is not None,
                "session_id": self.current_session.session_id if self.current_session else None,
                "timestamp": time.time(),
            }
            await websocket.send(json.dumps(reply))
        elif msg_type == "dev_set_state":
            target_state = data.get("state")
            valid_dev_states = (
                "hidden", "wake", "listening", "processing", "speaking",
                "agent_thinking", "agent_acting", "agent_verifying", "closing"
            )
            if target_state in valid_dev_states:
                if target_state == "wake":
                    self.emit_wake()
                elif target_state == "closing":
                    self.emit_closing()
                elif target_state == "hidden":
                    self.end_session()
                else:
                    self.set_state(target_state)
        elif msg_type == "dev_end_session":
            self.emit_closing()

    def _broadcast_json(self, payload: dict):
        """Thread-safe broadcast JSON payload to all connected WebSocket clients."""
        if not self.loop or not self.running:
            return

        msg_str = json.dumps(payload)

        async def _send_all():
            if not self.clients:
                return
            disconnected = set()
            for client in list(self.clients):
                try:
                    await client.send(msg_str)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(client)
                except Exception as ex:
                    log.debug("Broadcast error to client: %s", ex)
                    disconnected.add(client)
            self.clients.difference_update(disconnected)

        asyncio.run_coroutine_threadsafe(_send_all(), self.loop)

    def is_conversation_active(self) -> bool:
        """Check if an interactive conversation session is currently active."""
        with self._lock:
            return self.current_session is not None and self.current_state not in ("hidden", "closing")

    def emit_wake(self, session_id: str | None = None) -> str:
        """Triggered when the dedicated conversation phrase ('Hey Jarvis, I need your help') is recognized."""
        with self._lock:
            self.current_session = JarvisSession(session_id)
            self.current_state = "wake"
            active_id = self.current_session.session_id
            log.info("[JARVIS] Wake detected -> Conversation session acquired. ID: %s", active_id)

        self._broadcast_json({
            "type": "wake_detected",
            "session_id": active_id,
            "timestamp": time.time()
        })
        return active_id

    def set_state(self, state: str) -> None:
        """Explicitly change the runtime state (hidden, wake, listening, processing, speaking, agent_thinking, agent_acting, agent_verifying, closing)."""
        valid_states = (
            "hidden", "wake", "listening", "processing", "speaking",
            "agent_thinking", "agent_acting", "agent_verifying", "closing"
        )
        if state not in valid_states:
            log.warning("[JARVIS] Invalid state requested: %s", state)
            return

        with self._lock:
            # If session is inactive/closing/hidden, only allow "hidden" or "closing"
            if self.current_session is None or self.current_state in ("closing", "hidden"):
                if state not in ("hidden", "closing"):
                    log.debug("[JARVIS] Ignored state change to '%s' because conversation session is not active.", state)
                    return

            self.current_state = state
            if self.current_session:
                self.current_session.touch()
                self.current_session.state = state
            log.info("[JARVIS] State changed -> %s", state)

        self._broadcast_json({
            "type": "state_changed",
            "state": state,
            "timestamp": time.time()
        })

    def emit_agent_event(self, event_type: str, payload: dict | None = None) -> None:
        """Broadcast intermediate agent event (thinking, tool execution, verification) to UI clients."""
        with self._lock:
            if self.current_session:
                self.current_session.touch()

        self._broadcast_json({
            "type": "agent_event",
            "event_type": event_type,
            "payload": payload or {},
            "session_id": self.current_session.session_id if self.current_session else None,
            "timestamp": time.time(),
        })

    def emit_audio_level(self, level: float) -> None:
        """Broadcast live microphone input amplitude (normalized 0.0 - 1.0) with rate limiting."""
        if self.current_state != "listening":
            return
        now = time.monotonic()
        if now - self._last_audio_broadcast < 0.033:
            return
        self._last_audio_broadcast = now

        clamped = max(0.0, min(1.0, float(level)))
        self._broadcast_json({
            "type": "audio_level",
            "value": round(clamped, 3)
        })

    def emit_tts_level(self, level: float) -> None:
        """Broadcast live speech playback amplitude (normalized 0.0 - 1.0) with rate limiting."""
        if self.current_state != "speaking":
            return
        now = time.monotonic()
        if now - self._last_tts_broadcast < 0.033:
            return
        self._last_tts_broadcast = now

        clamped = max(0.0, min(1.0, float(level)))
        self._broadcast_json({
            "type": "tts_audio_level",
            "value": round(clamped, 3)
        })

    def emit_closing(self) -> None:
        """Triggered on voice close/sleep command ('Jarvis, go to sleep'). Plays closing animation before hiding."""
        with self._lock:
            if self.current_state in ("hidden", "closing"):
                return
            self.current_state = "closing"
            self.current_session = None  # Immediately invalidate session lock
            log.info("[JARVIS] Sleep/Close command detected -> Orb closing animation initiated.")

        self._broadcast_json({
            "type": "state_changed",
            "state": "closing",
            "timestamp": time.time()
        })

        def _deferred_end():
            time.sleep(0.65)
            self.end_session()

        threading.Thread(target=_deferred_end, daemon=True).start()

    def end_session(self) -> None:
        """Terminate the active conversation session and set state to hidden."""
        with self._lock:
            self.current_session = None
            self.current_state = "hidden"
            log.info("[JARVIS] Session ended -> UI hidden. Background wake detector ready.")

        self._broadcast_json({
            "type": "session_ended",
            "state": "hidden",
            "timestamp": time.time()
        })
        self._broadcast_json({
            "type": "state_changed",
            "state": "hidden",
            "timestamp": time.time()
        })

    def touch_session(self) -> None:
        """Keep the session alive upon user activity."""
        with self._lock:
            if self.current_session:
                self.current_session.touch()

    def _session_expiration_loop(self):
        """Background thread to monitor session inactivity and auto-hide UI."""
        while self.running:
            time.sleep(1.0)
            if self.current_session and self.current_state == "listening":
                if self.current_session.is_expired(self.session_timeout_s):
                    log.info("[JARVIS] Inactivity timeout (%.1fs) reached -> Going to sleep.", self.session_timeout_s)
                    self.emit_closing()

    def stop(self) -> None:
        """Gracefully stop the WebSocket server."""
        self.running = False
        if self.loop and self.loop.is_running():
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
            except Exception:
                pass

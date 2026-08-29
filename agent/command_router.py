"""
Command Router: Intelligently dispatches user utterances to either
Deterministic Actions (Trigger/Quick actions) or Hermes Agent (Complex tasks)
using the rich VoiceNormalizationPipeline.
"""

from __future__ import annotations

from enum import Enum
import logging
from typing import Any

from .normalizer import InterpretationContext, VoiceNormalizationPipeline
from .voice_memory import VoiceMemory

log = logging.getLogger("command_router")


class RouteTarget(str, Enum):
    """Destination target for an utterance."""
    DETERMINISTIC_ACTION = "DETERMINISTIC_ACTION"
    HERMES_AGENT = "HERMES_AGENT"
    SLEEP_DISMISS = "SLEEP_DISMISS"
    IGNORE = "IGNORE"
    UNKNOWN = "UNKNOWN"


class CommandRouter:
    """
    Evaluates transcript text to avoid unnecessary LLM overhead for known deterministic commands
    while routing complex or natural language instructions to Hermes Agent.
    Filters out background noise and filler words to prevent spam.
    """

    FILLER_NOISE_WORDS = {
        "ah", "oh", "um", "uh", "eh", "er", "hm", "hmm", "mm", "the", "a",
        "so", "yeah", "no", "oh up", "what a man", "right yeah no", "you know i know",
        "yeah this", "oh yeah", "now", "up", "ạ", "ờ", "ừ", "hả", "nè"
    }

    WINDOW_CLOSE_PHRASES = (
        "close_window", "close window", "close windows", "closed window", "close the window",
        "close current window", "close tab", "close browser", "close chrome",
        "close youtube", "close app", "close application", "close program",
        "dong cua so", "tat cua so", "dong tab", "tat tab", "dong lai", "quit window", "tat app"
    )

    SLEEP_PHRASES = (
        "go to sleep", "to sleep", "jarvis sleep", "jarvis go to sleep", "sleep now",
        "dismiss jarvis", "close jarvis", "goodbye jarvis", "bye jarvis", "goodbye",
        "bye bye", "will slip", "cabbies", "di ngu di", "tat di"
    )

    # Pure deterministic commands without multi-step conjunctions
    DETERMINISTIC_MAP = {
        "open_spotify": ("open spotify", "play spotify", "start spotify", "play music", "play song"),
        "open_vscode": ("open vs code", "open vscode", "open code", "launch vscode"),
        "open_chrome": ("open chrome", "open browser", "launch chrome", "open graham", "opened graham", "poland graham"),
        "open_antigravity": ("open antigravity", "launch antigravity"),
        "open_cursor": ("open cursor", "launch cursor"),
    }

    @classmethod
    def route(
        cls,
        text: str,
        active_context: dict[str, Any] | None = None,
        interpretation: InterpretationContext | None = None,
    ) -> tuple[RouteTarget, str, dict[str, Any]]:
        """
        Route an incoming recognized speech string.
        Returns:
            (target: RouteTarget, action_or_intent: str, metadata: dict)
        """
        if not text or len(text.strip()) < 2:
            return RouteTarget.IGNORE, "empty_or_too_short", {"raw_transcript": text}

        # 1. Process through Voice Normalization & Interpretation Pipeline
        pipeline = VoiceNormalizationPipeline.get_instance()
        ctx: InterpretationContext = interpretation or pipeline.process_transcript(text, active_context=active_context)
        cleaned = ctx.normalized_transcript.strip().lower()

        # 2. Filter out filler noises and short ambient fragments
        if cleaned in cls.FILLER_NOISE_WORDS or ctx.raw_transcript.strip().lower() in cls.FILLER_NOISE_WORDS:
            log.info("[ROUTER] Filtered out ambient noise/filler phrase: '%s'", text)
            return RouteTarget.IGNORE, "filler_noise", ctx.to_dict()

        # 3. Sleep & Close session commands (Closing Jarvis UI / session)
        if ctx.intent == "SLEEP_DISMISS" or any(sp in cleaned for sp in cls.SLEEP_PHRASES) or cleaned in ("sleep", "dismiss", "tat di"):
            log.info("[ROUTER] Detected sleep/close command in '%s'", text)
            return RouteTarget.SLEEP_DISMISS, "sleep", ctx.to_dict()

        # 4. Desktop Window Closing Command (Must NOT close Jarvis itself) -> Route to Hermes Agent
        if ctx.intent == "CLOSE_APPLICATION" or any(wcp in cleaned for wcp in cls.WINDOW_CLOSE_PHRASES):
            log.info("[ROUTER] Detected desktop window close request '%s' -> Routing to Hermes Agent", text)
            return RouteTarget.HERMES_AGENT, "agent_task", {
                "instruction": text,
                "normalized": ctx.normalized_transcript,
                "interpretation": ctx.to_dict(),
            }

        # 5. Fast-Path Deterministic Single-App Launch Commands
        if ctx.intent == "OPEN_APPLICATION" and not ctx.is_compound and ctx.confidence >= 0.70 and ctx.target_entity:
            canonical_id = ctx.target_entity.canonical_id
            if canonical_id == "vscode":
                log.info("[ROUTER] Fast-path routing to 'open_vscode' for '%s'", text)
                return RouteTarget.DETERMINISTIC_ACTION, "open_vscode", ctx.to_dict()
            elif canonical_id == "chrome":
                log.info("[ROUTER] Fast-path routing to 'open_chrome' for '%s'", text)
                return RouteTarget.DETERMINISTIC_ACTION, "open_chrome", ctx.to_dict()
            elif canonical_id == "antigravity":
                log.info("[ROUTER] Fast-path routing to 'open_antigravity' for '%s'", text)
                return RouteTarget.DETERMINISTIC_ACTION, "open_antigravity", ctx.to_dict()
            elif canonical_id == "cursor":
                log.info("[ROUTER] Fast-path routing to 'open_cursor' for '%s'", text)
                return RouteTarget.DETERMINISTIC_ACTION, "open_cursor", ctx.to_dict()
            elif canonical_id == "spotify":
                log.info("[ROUTER] Fast-path routing to 'open_spotify' for '%s'", text)
                return RouteTarget.DETERMINISTIC_ACTION, "open_spotify", ctx.to_dict()
            else:
                # Other known installed apps
                log.info("[ROUTER] Fast-path routing to 'open_app:%s' for '%s'", canonical_id, text)
                return RouteTarget.DETERMINISTIC_ACTION, f"open_app:{canonical_id}", ctx.to_dict()

        # 6. Fast-Path Deterministic Media Control (Spotify / Music)
        if ctx.intent == "MEDIA_CONTROL" and not ctx.is_compound and any(sk in cleaned for sk in ("spotify", "nhạc", "bài hát", "song", "music", "play spotify")):
            log.info("[ROUTER] Fast-path routing to 'open_spotify' for media command '%s'", text)
            return RouteTarget.DETERMINISTIC_ACTION, "open_spotify", ctx.to_dict()

        # 7. Check legacy deterministic string map for exact backward compatibility
        if not ctx.is_compound:
            for action_key, phrases in cls.DETERMINISTIC_MAP.items():
                for p in phrases:
                    if cleaned == p or cleaned.startswith(f"{p} ") or cleaned.endswith(f" {p}"):
                        log.info("[ROUTER] Fast-path routing to deterministic action '%s'", action_key)
                        return RouteTarget.DETERMINISTIC_ACTION, action_key, ctx.to_dict()

        # 8. Default to Hermes Agent for reasoning, computer use, and compound instructions
        log.info("[ROUTER] Routing natural-language task '%s' to Hermes Agent", text)
        return RouteTarget.HERMES_AGENT, "agent_task", {
            "instruction": text,
            "normalized": ctx.normalized_transcript,
            "interpretation": ctx.to_dict(),
        }

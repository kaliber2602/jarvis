"""
Qwen LLM Provider for Jarvis:
Handles complex natural-language reasoning, multi-step planning, tool selection,
and synthesizing concise, polite English voice responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
import re
from typing import Any, List, Optional
import httpx

log = logging.getLogger("qwen_provider")


@dataclass
class LLMPlanResult:
    """Structured plan output from Qwen LLM reasoning."""
    actions: list[dict[str, Any]] = field(default_factory=list)
    speech_response: str = ""
    intent: str = "general"
    reasoning: str = ""
    confidence: float = 1.0


class QwenProvider:
    """
    Qwen LLM Integration:
    Connects to local Qwen (Ollama / vLLM) or remote OpenAI-compatible API.
    """

    _instance: QwenProvider | None = None

    @classmethod
    def get_instance(cls) -> QwenProvider:
        if cls._instance is None:
            cls._instance = QwenProvider()
        return cls._instance

    def __init__(self):
        self.api_url = os.environ.get("QWEN_API_URL", os.environ.get("LLM_API_URL", "")).strip()
        self.api_key = os.environ.get("QWEN_API_KEY", os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))).strip()
        self.model = os.environ.get("QWEN_MODEL", os.environ.get("LLM_MODEL", "qwen2.5:7b")).strip()
        self.timeout_s = float(os.environ.get("LLM_TIMEOUT", "10.0"))

    def is_available(self) -> bool:
        return bool(self.api_url)

    def generate_plan(
        self,
        instruction: str,
        available_tools: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> Optional[LLMPlanResult]:
        """
        Query Qwen LLM to reason over user instruction and select required tool actions.
        Returns None if remote API is unavailable or returns an error.
        """
        if not self.is_available():
            return None

        tools_description = "\n".join(
            f"- {t.get('name')}: {t.get('description')} (params: {list(t.get('parameters', {}).get('properties', {}).keys())})"
            for t in available_tools
        )

        system_prompt = (
            "You are Jarvis, a brilliant, concise desktop AI assistant.\n"
            "Analyze the user's spoken command (which may be in English, Vietnamese, or Mixed) and produce an action plan.\n"
            "Always formulate your final speech response in fluent, natural ENGLISH.\n\n"
            f"Available tools:\n{tools_description}\n\n"
            "Respond STRICTLY in valid JSON format with this exact schema:\n"
            "{\n"
            '  "intent": "<short intent name>",\n'
            '  "reasoning": "<1 sentence reasoning>",\n'
            '  "actions": [\n'
            '    {"tool": "<tool_name>", "params": {<parameters>}}\n'
            "  ],\n"
            '  "speech_response": "<Natural concise English response to say to the user>"\n'
            "}"
        )

        user_content = f"User Command: {instruction}"
        if context:
            user_content += f"\nActive Context: {json.dumps(context, ensure_ascii=False)}"

        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.1,
                "max_tokens": 300,
            }

            url = f"{self.api_url.rstrip('/')}/chat/completions"
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"].strip()

                    # Extract JSON object
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        actions = parsed.get("actions", [])
                        speech = parsed.get("speech_response", "")
                        intent = parsed.get("intent", "general")
                        reasoning = parsed.get("reasoning", "")
                        log.info("[LLM] Qwen plan generated: intent='%s' | speech='%s' | tools=%s", intent, speech, [a.get("tool") for a in actions])
                        return LLMPlanResult(
                            actions=actions,
                            speech_response=speech,
                            intent=intent,
                            reasoning=reasoning,
                            confidence=0.95,
                        )
        except Exception as e:
            log.debug("[LLM] Qwen remote reasoning skipped/failed: %s", e)

        return None


def get_llm_provider() -> QwenProvider:
    return QwenProvider.get_instance()

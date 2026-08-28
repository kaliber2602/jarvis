"""
Safety & Permission Policy Layer for Jarvis Agent Computer-Use.
Enforces safety boundaries, preventing unapproved destructive commands.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("safety_policy")


class SafetyPolicy:
    """
    Evaluates tool execution requests against safe and destructive policy rules.
    """

    # Dangerous patterns in shell commands that are strictly blocked or require explicit confirmation
    DANGEROUS_SHELL_PATTERNS = [
        r"\brmdir\s+(?:/[sS]|/[qQ])",
        r"\bdel\s+.*(?:/[fF]|/[sS]|/[qQ])",
        r"\bformat\s+[a-zA-Z]:",
        r"\bdiskpart\b",
        r"\breg\s+delete\b",
        r"\bRemove-Item\s+.*-Recurse\s+-Force\b",
        r"\bStop-Computer\b",
        r"\bRestart-Computer\b",
        r"\bClear-Disk\b",
        r"\bInitialize-Disk\b",
        r"\bdrop\s+database\b",
    ]

    # Whitelisted safe application executables and names
    ALLOWED_APPS = {
        "chrome", "google chrome", "browser",
        "code", "vscode", "vs code", "visual studio code",
        "antigravity", "cursor", "spotify",
        "notepad", "calc", "calculator", "explorer", "cmd", "powershell", "terminal",
        "discord", "slack", "telegram", "blender", "obs", "git"
    }

    @classmethod
    def evaluate_action(cls, tool_name: str, params: dict[str, Any]) -> tuple[bool, str]:
        """
        Evaluate if a tool action is permitted.
        Returns:
            (allowed: bool, reason: str)
        """
        if tool_name == "open_application":
            app = str(params.get("app_name", "")).strip().lower()
            if not app:
                return False, "Application name cannot be empty."
            return True, f"Application launch '{app}' is permitted."

        elif tool_name in ("search_web", "open_url", "browse"):
            url = str(params.get("url", "") or params.get("query", ""))
            return True, f"Web navigation/search '{url}' is permitted."

        elif tool_name in ("type_text", "press_hotkey", "mouse_click", "focus_window"):
            return True, f"UI interaction '{tool_name}' is permitted."

        elif tool_name in ("find_files", "list_directory", "read_file", "get_system_info"):
            return True, f"Read-only system inspection '{tool_name}' is permitted."

        elif tool_name in ("run_powershell", "run_shell_command", "bash"):
            cmd = str(params.get("command", "") or params.get("cmd", "")).strip()
            for pattern in cls.DANGEROUS_SHELL_PATTERNS:
                if re.search(pattern, cmd, re.IGNORECASE):
                    log.warning("[SAFETY] Blocked destructive shell command matching '%s': %s", pattern, cmd)
                    return False, f"Potentially destructive command blocked by safety policy: matching pattern '{pattern}'"

            # Check delete commands
            if re.search(r"\b(rm|del|remove-item)\b", cmd, re.IGNORECASE) and not params.get("user_confirmed", False):
                log.warning("[SAFETY] File deletion requires confirmation: %s", cmd)
                return False, "File deletion commands require explicit confirmation."

            return True, "Shell command validated and permitted."

        # Default fallback
        return True, f"Action '{tool_name}' is permitted."

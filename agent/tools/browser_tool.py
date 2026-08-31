"""
Browser and Web Navigation Tool for Hermes Agent.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import urllib.parse
import webbrowser
from typing import Any

from ..safety_policy import SafetyPolicy

log = logging.getLogger("browser_tool")


class BrowserTool:
    """
    Automates web navigation, Chrome browser tabs, and search engines.
    """

    JARVIS_CHROME_PROFILE = os.path.join(os.environ.get("LOCALAPPDATA", "C:\\"), "Jarvis", "ChromeProfile")
    CDP_PORT = 9222

    @classmethod
    def _chrome_executable(cls) -> str | None:
        if sys.platform == "win32":
            for base in (
                os.environ.get("ProgramFiles", r"C:\Program Files"),
                os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                os.environ.get("LOCALAPPDATA", ""),
            ):
                if not base:
                    continue
                p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
                if os.path.isfile(p):
                    return p
        return shutil.which("google-chrome") or shutil.which("chrome")

    @classmethod
    def open_url(cls, url: str, new_window: bool = False) -> dict[str, Any]:
        """Open a web URL in Google Chrome with Isolated CDP Profile or default browser."""
        allowed, reason = SafetyPolicy.evaluate_action("open_url", {"url": url})
        if not allowed:
            return {"success": False, "error": reason}

        u = url.strip()
        if not u.startswith("http://") and not u.startswith("https://"):
            u = "https://" + u

        try:
            chrome_exe = cls._chrome_executable()
            if chrome_exe and sys.platform == "win32":
                os.makedirs(cls.JARVIS_CHROME_PROFILE, exist_ok=True)
                args = [
                    chrome_exe,
                    f"--remote-debugging-port={cls.CDP_PORT}",
                    "--remote-allow-origins=*",
                    f"--user-data-dir={cls.JARVIS_CHROME_PROFILE}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
                if new_window:
                    args.append("--new-window")
                args.append(u)

                subprocess.Popen(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log.info("[BROWSER] Opened %s with Isolated CDP on port %d", u, cls.CDP_PORT)
                return {"success": True, "message": f"Opened {u} with Isolated CDP on port {cls.CDP_PORT}."}

            elif chrome_exe:
                args = [chrome_exe, f"--remote-debugging-port={cls.CDP_PORT}"]
                if new_window:
                    args.append("--new-window")
                args.append(u)
                subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log.info("[BROWSER] Opened URL in Chrome with CDP: %s", u)
                return {"success": True, "message": f"Opened {u} in Chrome with CDP."}

            elif sys.platform == "win32":
                os.startfile(u)
                log.info("[BROWSER] Fallback: Opened URL via os.startfile: %s", u)
                return {"success": True, "message": f"Opened {u} in browser."}

            else:
                webbrowser.open(u)
                log.info("[BROWSER] Opened URL in default browser: %s", u)
                return {"success": True, "message": f"Opened {u} in browser."}
        except Exception as e:
            log.warning("[BROWSER] Error opening URL: %s", e)
            try:
                webbrowser.open(u)
                return {"success": True, "message": f"Opened {u} in fallback browser."}
            except Exception as fb_err:
                return {"success": False, "error": str(fb_err)}

    @classmethod
    def search_web(cls, query: str, engine: str = "google") -> dict[str, Any]:
        """Perform a web search on Google, YouTube, or Bing."""
        q = query.strip()
        encoded = urllib.parse.quote_plus(q)

        engine_lower = engine.lower()
        if "youtube" in engine_lower:
            target_url = f"https://www.youtube.com/results?search_query={encoded}"
        elif "bing" in engine_lower:
            target_url = f"https://www.bing.com/search?q={encoded}"
        else:
            target_url = f"https://www.google.com/search?q={encoded}"

        log.info("[BROWSER] Searching %s for '%s' -> %s", engine, q, target_url)
        return cls.open_url(target_url, new_window=False)

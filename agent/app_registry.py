"""
Application & Technical Vocabulary Registry for Jarvis.
Provides:
1. Dynamic discovery of Windows installed applications from Start Menu, Registry, and PATH.
2. Curated developer & desktop application dictionary with phonetic & multilingual aliases.
3. Domain vocabulary for technical terms, frameworks, and web services.
4. Fast indexed lookup and entity candidate generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from .phonetics import remove_vietnamese_diacritics

log = logging.getLogger("app_registry")


@dataclass
class AppInfo:
    display_name: str
    normalized_name: str
    canonical_id: str
    executable: str
    path: str | None = None
    aliases: list[str] = field(default_factory=list)
    source: str = "curated"  # "curated" | "start_menu" | "registry" | "path"
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "normalized_name": self.normalized_name,
            "canonical_id": self.canonical_id,
            "executable": self.executable,
            "path": self.path,
            "aliases": self.aliases,
            "source": self.source,
            "description": self.description,
        }


class AppRegistry:
    """
    Central repository of known applications, technical entities, and system capabilities.
    """

    _instance: AppRegistry | None = None

    @classmethod
    def get_instance(cls) -> AppRegistry:
        if cls._instance is None:
            cls._instance = AppRegistry()
        return cls._instance

    def __init__(self):
        self.apps_by_id: dict[str, AppInfo] = {}
        self.alias_to_id: dict[str, str] = {}
        self.technical_terms: set[str] = set()

        # 1. Load curated apps
        self._load_curated_apps()

        # 2. Load technical domain vocabulary
        self._load_technical_vocabulary()

        # 3. Discover Windows installed apps
        if sys.platform == "win32":
            try:
                self.discover_windows_installed_apps()
            except Exception as e:
                log.warning("[APP_REGISTRY] Windows app discovery encountered error: %s", e)

        # 4. Build inverted alias index
        self._rebuild_indices()

    def _load_curated_apps(self) -> None:
        """Preload curated desktop apps and developer tools."""
        curated_list = [
            AppInfo(
                display_name="Visual Studio Code",
                normalized_name="visual studio code",
                canonical_id="vscode",
                executable="Code.exe",
                aliases=[
                    "vs code", "vscode", "visual studio code", "visual studio",
                    "viet code", "viết code", "viets code", "vietcode", "v s code",
                    "code", "visual code", "vs", "v s"
                ],
                source="curated",
                description="Code editor by Microsoft",
            ),
            AppInfo(
                display_name="Google Chrome",
                normalized_name="google chrome",
                canonical_id="chrome",
                executable="chrome.exe",
                aliases=[
                    "chrome", "google chrome", "chôm", "crôm", "cờ rôm", "trình duyệt",
                    "browser", "web browser", "graham", "google",
                    "chình duyệt", "chinh duyet", "trinh duyet", "xanh chình duyệt", "sang chình duyệt"
                ],
                source="curated",
                description="Web browser by Google",
            ),
            AppInfo(
                display_name="Cursor",
                normalized_name="cursor",
                canonical_id="cursor",
                executable="Cursor.exe",
                aliases=[
                    "cursor", "cursor editor", "cursor ai", "con trỏ", "con tro", "cơ xơ", "cơ xor"
                ],
                source="curated",
                description="AI Code Editor",
            ),
            AppInfo(
                display_name="Antigravity",
                normalized_name="antigravity",
                canonical_id="antigravity",
                executable="Antigravity.exe",
                aliases=[
                    "antigravity", "gravity", "anti gravity"
                ],
                source="curated",
                description="Antigravity Workspace",
            ),
            AppInfo(
                display_name="Discord",
                normalized_name="discord",
                canonical_id="discord",
                executable="Discord.exe",
                aliases=[
                    "discord", "đít cọt", "đít sờ cọt", "dit cot", "dis cọt"
                ],
                source="curated",
                description="Voice & text communication platform",
            ),
            AppInfo(
                display_name="Spotify",
                normalized_name="spotify",
                canonical_id="spotify",
                executable="Spotify.exe",
                aliases=[
                    "spotify", "sờ po ti phai", "sờ po ty phai", "music", "nhạc"
                ],
                source="curated",
                description="Music streaming player",
            ),
            AppInfo(
                display_name="Windows Terminal",
                normalized_name="windows terminal",
                canonical_id="terminal",
                executable="wt.exe",
                aliases=[
                    "terminal", "windows terminal", "term", "tơ mi nồ", "tơ min nồ", "console"
                ],
                source="curated",
                description="Windows Terminal Emulator",
            ),
            AppInfo(
                display_name="PowerShell",
                normalized_name="powershell",
                canonical_id="powershell",
                executable="powershell.exe",
                aliases=[
                    "powershell", "windows powershell", "pwsh", "pao eo sen"
                ],
                source="curated",
                description="PowerShell shell environment",
            ),
            AppInfo(
                display_name="Command Prompt",
                normalized_name="command prompt",
                canonical_id="cmd",
                executable="cmd.exe",
                aliases=[
                    "cmd", "command prompt", "cmd prompt", "cmd exe"
                ],
                source="curated",
                description="Windows Command Prompt",
            ),
            AppInfo(
                display_name="File Explorer",
                normalized_name="file explorer",
                canonical_id="explorer",
                executable="explorer.exe",
                aliases=[
                    "file explorer", "explorer", "windows explorer", "thư mục", "tập tin",
                    "my computer", "this pc", "files", "folder"
                ],
                source="curated",
                description="Windows File Explorer",
            ),
            AppInfo(
                display_name="Notion",
                normalized_name="notion",
                canonical_id="notion",
                executable="Notion.exe",
                aliases=[
                    "notion", "nốt son", "nô sơn", "notion app"
                ],
                source="curated",
                description="Notes and workspace tool",
            ),
            AppInfo(
                display_name="Figma",
                normalized_name="figma",
                canonical_id="figma",
                executable="Figma.exe",
                aliases=[
                    "figma", "phích ma", "figma design"
                ],
                source="curated",
                description="UI/UX Collaborative Design Tool",
            ),
            AppInfo(
                display_name="Docker Desktop",
                normalized_name="docker desktop",
                canonical_id="docker",
                executable="Docker Desktop.exe",
                aliases=[
                    "docker", "docker desktop", "đốc cơ", "doc co"
                ],
                source="curated",
                description="Docker container manager",
            ),
            AppInfo(
                display_name="YouTube",
                normalized_name="youtube",
                canonical_id="youtube",
                executable="chrome.exe",
                aliases=[
                    "youtube", "you tube", "u tube", "du túp", "du tup", "diu túp", "gu túp"
                ],
                source="curated",
                description="YouTube video streaming platform",
            ),
            AppInfo(
                display_name="Postman",
                normalized_name="postman",
                canonical_id="postman",
                executable="Postman.exe",
                aliases=[
                    "postman", "pốt man", "bốt man", "post man"
                ],
                source="curated",
                description="API testing tool",
            ),
            AppInfo(
                display_name="GitHub Desktop",
                normalized_name="github desktop",
                canonical_id="github",
                executable="GitHubDesktop.exe",
                aliases=[
                    "github desktop", "github", "git hub", "gít húp", "git"
                ],
                source="curated",
                description="Git repository manager",
            ),
            AppInfo(
                display_name="Steam",
                normalized_name="steam",
                canonical_id="steam",
                executable="steam.exe",
                aliases=[
                    "steam", "sờ tim"
                ],
                source="curated",
                description="Gaming platform",
            ),
            AppInfo(
                display_name="Mozilla Firefox",
                normalized_name="firefox",
                canonical_id="firefox",
                executable="firefox.exe",
                aliases=[
                    "firefox", "mozilla firefox", "cáo lửa"
                ],
                source="curated",
                description="Firefox browser",
            ),
            AppInfo(
                display_name="Microsoft Edge",
                normalized_name="microsoft edge",
                canonical_id="edge",
                executable="msedge.exe",
                aliases=[
                    "edge", "microsoft edge", "ms edge"
                ],
                source="curated",
                description="Microsoft Edge browser",
            ),
            AppInfo(
                display_name="Obsidian",
                normalized_name="obsidian",
                canonical_id="obsidian",
                executable="Obsidian.exe",
                aliases=[
                    "obsidian", "obsidian md"
                ],
                source="curated",
                description="Markdown knowledge base",
            ),
            AppInfo(
                display_name="Slack",
                normalized_name="slack",
                canonical_id="slack",
                executable="slack.exe",
                aliases=[
                    "slack", "sờ lác"
                ],
                source="curated",
                description="Team collaboration app",
            ),
            AppInfo(
                display_name="Telegram",
                normalized_name="telegram",
                canonical_id="telegram",
                executable="Telegram.exe",
                aliases=[
                    "telegram", "te le gram"
                ],
                source="curated",
                description="Messaging app",
            ),
            AppInfo(
                display_name="VLC Media Player",
                normalized_name="vlc media player",
                canonical_id="vlc",
                executable="vlc.exe",
                aliases=[
                    "vlc", "vlc media player", "vlc player"
                ],
                source="curated",
                description="VLC media player",
            ),
            AppInfo(
                display_name="Blender",
                normalized_name="blender",
                canonical_id="blender",
                executable="blender.exe",
                aliases=[
                    "blender", "blender 3d", "bờ len đơ"
                ],
                source="curated",
                description="3D creation suite",
            ),
            AppInfo(
                display_name="Notepad",
                normalized_name="notepad",
                canonical_id="notepad",
                executable="notepad.exe",
                aliases=[
                    "notepad", "ghi chú", "note pad"
                ],
                source="curated",
                description="Text editor",
            ),
            AppInfo(
                display_name="Calculator",
                normalized_name="calculator",
                canonical_id="calc",
                executable="calc.exe",
                aliases=[
                    "calculator", "calc", "máy tính"
                ],
                source="curated",
                description="Windows calculator",
            ),
        ]

        for app in curated_list:
            self.register_app(app)

    def _load_technical_vocabulary(self) -> None:
        """Domain technical terminology for context-aware interpretation."""
        self.technical_terms = {
            "python", "javascript", "typescript", "react", "fastapi", "django", "flask",
            "nodejs", "node", "npm", "yarn", "pnpm", "pip", "git", "github", "gitlab",
            "docker", "docker compose", "compose", "kubernetes", "k8s", "postgresql", "postgres",
            "mysql", "sqlite", "redis", "mongodb", "minio", "aws", "s3", "ec2", "lambda",
            "azure", "gcp", "api", "rest", "rest api", "graphql", "http", "https", "websocket",
            "json", "yaml", "xml", "csv", "html", "css", "tailwind", "nextjs", "vue",
            "chatgpt", "openai", "claude", "gemini", "anthropic", "llm", "ai", "ollama",
            "vscode", "terminal", "powershell", "bash", "zsh", "ssh", "ssl", "tls",
            "backend", "frontend", "fullstack", "database", "server", "client"
        }

    def register_app(self, app: AppInfo) -> None:
        """Register or update an application in the catalog."""
        self.apps_by_id[app.canonical_id] = app

    def discover_windows_installed_apps(self) -> None:
        """
        Scan Windows Start Menu shortcuts and standard folders to discover installed applications.
        """
        if sys.platform != "win32":
            return

        shortcut_roots = [
            Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]

        discovered_count = 0
        for root in shortcut_roots:
            if not root.is_dir():
                continue
            for lnk_path in root.rglob("*.lnk"):
                name = lnk_path.stem.strip()
                # Ignore uninstallers or help links
                lower_name = name.lower()
                if any(k in lower_name for k in ("uninstall", "gỡ cài đặt", "help", "readme", "website", "documentation")):
                    continue

                canonical_id = re.sub(r"[^a-z0-9_]+", "_", lower_name).strip("_")
                if not canonical_id or canonical_id in self.apps_by_id:
                    continue

                clean_name = re.sub(r"\s*\([^)]*\)", "", name).strip()
                aliases = [
                    lower_name,
                    clean_name.lower(),
                    remove_vietnamese_diacritics(lower_name),
                ]

                app = AppInfo(
                    display_name=clean_name,
                    normalized_name=clean_name.lower(),
                    canonical_id=canonical_id,
                    executable=f"{canonical_id}.exe",
                    path=str(lnk_path.resolve()),
                    aliases=list(dict.fromkeys(aliases)),
                    source="start_menu",
                    description=f"Installed Windows application: {clean_name}",
                )
                self.register_app(app)
                discovered_count += 1

        log.info("[APP_REGISTRY] Discovered %d Windows Start Menu applications.", discovered_count)

    def _rebuild_indices(self) -> None:
        """Rebuild inverted index from aliases to canonical IDs."""
        self.alias_to_id.clear()
        for app_id, app in self.apps_by_id.items():
            # Add canonical ID
            self.alias_to_id[app.canonical_id.lower()] = app_id
            self.alias_to_id[app.normalized_name.lower()] = app_id
            self.alias_to_id[remove_vietnamese_diacritics(app.normalized_name.lower())] = app_id

            # Add all aliases
            for alias in app.aliases:
                a_clean = alias.strip().lower()
                if a_clean:
                    self.alias_to_id[a_clean] = app_id
                    self.alias_to_id[remove_vietnamese_diacritics(a_clean)] = app_id

    def get_app(self, app_id: str) -> AppInfo | None:
        """Get AppInfo by canonical ID."""
        return self.apps_by_id.get(app_id)

    def find_by_exact_alias(self, alias: str) -> AppInfo | None:
        """Lookup by exact alias (case-insensitive & diacritic-stripped)."""
        clean = alias.strip().lower()
        if clean in self.alias_to_id:
            return self.apps_by_id.get(self.alias_to_id[clean])
        no_accent = remove_vietnamese_diacritics(clean)
        if no_accent in self.alias_to_id:
            return self.apps_by_id.get(self.alias_to_id[no_accent])
        return None

    def get_all_apps(self) -> list[AppInfo]:
        """Return list of all registered applications."""
        return list(self.apps_by_id.values())

    def is_technical_term(self, term: str) -> bool:
        """Check if a word is in technical domain vocabulary."""
        return term.strip().lower() in self.technical_terms

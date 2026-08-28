"""
System and File Inspection Tool for Hermes Agent.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import psutil
from typing import Any

from ..safety_policy import SafetyPolicy

log = logging.getLogger("system_tool")


class SystemTool:
    """
    Read-only system information, file discovery, and status tools.
    """

    @classmethod
    def get_known_folder(cls, name: str) -> Path:
        """Resolve common user folder paths."""
        home = Path.home()
        name_lower = name.lower()
        if "download" in name_lower:
            return home / "Downloads"
        elif "document" in name_lower:
            return home / "Documents"
        elif "desktop" in name_lower:
            return home / "Desktop"
        elif "picture" in name_lower:
            return home / "Pictures"
        elif "music" in name_lower:
            return home / "Music"
        elif "video" in name_lower:
            return home / "Videos"
        return home

    @classmethod
    def find_latest_file(cls, folder: str = "Downloads", extension: str | None = None) -> dict[str, Any]:
        """Find the most recently modified/downloaded file in a directory."""
        dir_path = cls.get_known_folder(folder)
        if not dir_path.is_dir():
            return {"success": False, "error": f"Directory not found: {dir_path}"}

        try:
            files = [f for f in dir_path.iterdir() if f.is_file()]
            if extension:
                ext_clean = extension.lstrip(".").lower()
                files = [f for f in files if f.suffix.lstrip(".").lower() == ext_clean]

            if not files:
                return {"success": False, "message": f"No matching files found in {folder}."}

            latest = max(files, key=lambda f: f.stat().st_mtime)
            log.info("[SYSTEM] Found latest file in %s: %s", folder, latest.name)
            return {
                "success": True,
                "path": str(latest.resolve()),
                "filename": latest.name,
                "size_bytes": latest.stat().st_size,
                "modified_time": latest.stat().st_mtime,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def get_system_status(cls) -> dict[str, Any]:
        """Retrieve CPU, RAM, disk, and battery telemetry."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(os.path.abspath(os.sep))
            battery = psutil.sensors_battery()

            return {
                "success": True,
                "cpu_percent": cpu_percent,
                "memory_used_gb": round((mem.total - mem.available) / (1024**3), 2),
                "memory_total_gb": round(mem.total / (1024**3), 2),
                "memory_percent": mem.percent,
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "battery_percent": battery.percent if battery else None,
                "power_plugged": battery.power_plugged if battery else None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

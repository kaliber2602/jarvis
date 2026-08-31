"""
Process Manager: Dedicated OS Process Management Subsystem.
Strictly isolates Operating System Process Lifecycle from UI Window / HWND concepts.
Manages PID tracking, parent-child relationships, process trees, and state-based waiting.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

log = logging.getLogger("hermes.process_manager")

try:
    import psutil
except ImportError:
    psutil = None


@dataclass
class ProcessInfo:
    """Represents metadata of an active or queried OS process."""
    pid: int
    name: str = ""
    executable: str = ""
    parent_pid: Optional[int] = None
    create_time: float = 0.0
    status: str = "running"
    cmdline: list[str] = field(default_factory=list)

    @property
    def is_alive(self) -> bool:
        if not self.pid or not psutil:
            return False
        try:
            return psutil.pid_exists(self.pid)
        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "name": self.name,
            "executable": self.executable,
            "parent_pid": self.parent_pid,
            "create_time": round(self.create_time, 2),
            "status": self.status,
            "is_alive": self.is_alive,
        }


class ProcessManager:
    """
    Dedicated manager for operating system processes.
    Enforces the fundamental architectural invariant: A PROCESS IS NOT A WINDOW.
    """

    BROWSER_EXE_NAMES = {
        "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe",
        "google-chrome", "chrome", "firefox", "msedge", "brave"
    }

    @classmethod
    def get_process(cls, pid: int) -> Optional[ProcessInfo]:
        """Retrieve detailed process metadata by PID."""
        if not pid or not psutil:
            return None
        try:
            if not psutil.pid_exists(pid):
                return None
            p = psutil.Process(pid)
            if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                return None

            name = p.name()
            exe = ""
            try:
                exe = p.exe()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                exe = name

            ppid = None
            try:
                ppid = p.ppid()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

            ctime = 0.0
            try:
                ctime = p.create_time()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

            cmd = []
            try:
                cmd = p.cmdline()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

            return ProcessInfo(
                pid=pid,
                name=name,
                executable=exe,
                parent_pid=ppid,
                create_time=ctime,
                status=p.status(),
                cmdline=cmd,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as ex:
            log.debug("[PROCESS] Error querying PID %d: %s", pid, ex)
            return None

    @classmethod
    def is_running(cls, pid: int) -> bool:
        """Check whether a process with the given PID is currently active."""
        if not pid or not psutil:
            return False
        try:
            if not psutil.pid_exists(pid):
                return False
            p = psutil.Process(pid)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except Exception:
            return False

    @classmethod
    def find_processes_by_name(cls, name_pattern: str) -> list[ProcessInfo]:
        """Find all active processes matching a name substring."""
        if not psutil:
            return []
        pattern = name_pattern.strip().lower()
        results: list[ProcessInfo] = []

        try:
            for p in psutil.process_iter(['pid', 'name', 'ppid', 'create_time', 'status']):
                try:
                    p_name = (p.info.get('name') or "").lower()
                    if pattern in p_name:
                        info = cls.get_process(p.info['pid'])
                        if info:
                            results.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as ex:
            log.warning("[PROCESS] Error searching processes for '%s': %s", name_pattern, ex)

        return results

    @classmethod
    def get_children(cls, pid: int, recursive: bool = True) -> list[ProcessInfo]:
        """Get all child processes spawned by a given PID."""
        if not pid or not psutil:
            return []
        children: list[ProcessInfo] = []
        try:
            p = psutil.Process(pid)
            for child in p.children(recursive=recursive):
                try:
                    info = cls.get_process(child.pid)
                    if info:
                        children.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as ex:
            log.debug("[PROCESS] Error getting children of PID %d: %s", pid, ex)
        return children

    @classmethod
    def get_parent(cls, pid: int) -> Optional[ProcessInfo]:
        """Get parent process of a given PID."""
        if not pid or not psutil:
            return None
        try:
            p = psutil.Process(pid)
            parent = p.parent()
            if parent:
                return cls.get_process(parent.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            pass
        return None

    @classmethod
    def is_browser_process(cls, pid: int) -> bool:
        """Check whether a PID belongs to a known web browser process."""
        info = cls.get_process(pid)
        if not info:
            return False
        p_name = info.name.lower()
        return any(b in p_name for b in cls.BROWSER_EXE_NAMES)

    @classmethod
    def wait_until_running(
        cls,
        name_pattern: str,
        timeout: float = 5.0,
        interval: float = 0.1,
    ) -> Optional[ProcessInfo]:
        """State-based waiting until a process matching name_pattern is running."""
        deadline = time.time() + max(0.1, timeout)
        while time.time() < deadline:
            matches = cls.find_processes_by_name(name_pattern)
            if matches:
                return matches[0]
            time.sleep(interval)
        return None

    @classmethod
    def wait_until_exit(
        cls,
        pid: int,
        timeout: float = 5.0,
        interval: float = 0.1,
    ) -> bool:
        """State-based waiting until a process with the given PID terminates."""
        deadline = time.time() + max(0.1, timeout)
        while time.time() < deadline:
            if not cls.is_running(pid):
                return True
            time.sleep(interval)
        return not cls.is_running(pid)

    @classmethod
    def terminate_process(cls, pid: int, timeout: float = 3.0) -> bool:
        """Terminate a process gracefully, falling back to kill."""
        if not pid or not psutil or not cls.is_running(pid):
            return True
        try:
            p = psutil.Process(pid)
            p.terminate()
            p.wait(timeout=timeout)
            return True
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            try:
                p.kill()
                return True
            except Exception:
                return False
        except Exception:
            return False

"""OS-independent process matching and platform-specific enforcement."""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass

# Names a root agent must never stop. Short patterns would otherwise take down the machine.
PROTECTED_PROCESS_NAMES = {
    "init",
    "systemd",
    "sshd",
    "launchd",
    "kernel_task",
    "system",
    "csrss.exe",
    "lsass.exe",
    "services.exe",
    "smss.exe",
    "wininit.exe",
    "winlogon.exe",
}


@dataclass
class RunningProcess:
    pid: int
    name: str


def detect_os() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return "unknown"


def list_processes() -> list[RunningProcess]:
    os_name = detect_os()
    if os_name == "windows":
        return _list_windows()
    return _list_posix()


def _list_posix() -> list[RunningProcess]:
    try:
        out = subprocess.check_output(["ps", "-A", "-o", "pid=,comm="], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    procs: list[RunningProcess] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        name = parts[1].strip()
        # basename for paths
        if "/" in name:
            name = name.rsplit("/", 1)[-1]
        procs.append(RunningProcess(pid=pid, name=name))
    return procs


def _list_windows() -> list[RunningProcess]:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            text=True,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return []
    procs: list[RunningProcess] = []
    for line in out.splitlines():
        # "name.exe","PID","Session","Session#","Mem"
        m = re.match(r'^"([^"]+)","(\d+)"', line.strip())
        if not m:
            continue
        procs.append(RunningProcess(pid=int(m.group(2)), name=m.group(1)))
    return procs


def is_protected_process(pid: int, name: str) -> bool:
    """The system agent must not kill itself, pid 1, or core OS processes."""
    if pid <= 1 or pid == os.getpid():
        return True
    return name.lower() in PROTECTED_PROCESS_NAMES


def matches_rule(process_name: str, pattern: str, match_mode: str) -> bool:
    name = process_name.lower()
    pat = pattern.lower()
    if match_mode == "exact":
        return name == pat or name == f"{pat}.exe"
    if match_mode == "startswith":
        return name.startswith(pat)
    return pat in name


def find_matching_pids(rules: list[dict]) -> list[tuple[int, str, str]]:
    """Return (pid, process_name, rule_label) for processes matching any rule."""
    hits: list[tuple[int, str, str]] = []
    procs = list_processes()
    for proc in procs:
        if is_protected_process(proc.pid, proc.name):
            continue
        for rule in rules:
            if matches_rule(proc.name, rule.get("pattern", ""), rule.get("match_mode", "contains")):
                hits.append((proc.pid, proc.name, rule.get("label") or rule.get("pattern") or ""))
                break
    return hits


def kill_pid(pid: int, *, dry_run: bool = False) -> bool:
    if dry_run:
        return True
    os_name = detect_os()
    try:
        if os_name == "windows":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
        else:
            subprocess.run(["kill", "-TERM", str(pid)], check=False, capture_output=True)
        return True
    except Exception:
        return False


def notify(title: str, message: str, *, dry_run: bool = False) -> None:
    if dry_run:
        print(f"[notify] {title}: {message}")
        return
    os_name = detect_os()
    try:
        if os_name == "linux":
            subprocess.run(["notify-send", title, message], check=False, capture_output=True)
        elif os_name == "macos":
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
        elif os_name == "windows":
            # Best-effort balloon via PowerShell
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                f"[System.Windows.Forms.MessageBox]::Show('{message}','{title}')"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False, capture_output=True)
    except Exception:
        pass


def _lock_windows() -> None:
    """Lock the interactive desktop. From a SYSTEM service, start the lock in that session."""
    subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False, capture_output=True)
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
    session_id = kernel32.WTSGetActiveConsoleSessionId()
    if session_id == 0xFFFFFFFF:
        return
    user_token = wintypes.HANDLE()
    wtsapi32.WTSQueryUserToken.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    wtsapi32.WTSQueryUserToken.restype = wintypes.BOOL
    if not wtsapi32.WTSQueryUserToken(session_id, ctypes.byref(user_token)):
        return
    primary = wintypes.HANDLE()
    token_all_access = 0xF01FF
    if not advapi32.DuplicateTokenEx(user_token, token_all_access, None, 2, 1, ctypes.byref(primary)):
        kernel32.CloseHandle(user_token)
        return

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    info = STARTUPINFO()
    info.cb = ctypes.sizeof(STARTUPINFO)
    info.lpDesktop = "winsta0\\default"
    process = PROCESS_INFORMATION()
    command = ctypes.create_unicode_buffer("rundll32.exe user32.dll,LockWorkStation")
    advapi32.CreateProcessAsUserW(
        primary,
        None,
        command,
        None,
        None,
        False,
        0x08000000,
        None,
        None,
        ctypes.byref(info),
        ctypes.byref(process),
    )
    if process.hProcess:
        kernel32.CloseHandle(process.hProcess)
    if process.hThread:
        kernel32.CloseHandle(process.hThread)
    kernel32.CloseHandle(primary)
    kernel32.CloseHandle(user_token)


def lock_session(*, dry_run: bool = False) -> None:
    """Best-effort session lock / screen lock when access is denied."""
    if dry_run:
        print("[lock] session lock requested")
        return
    os_name = detect_os()
    try:
        if os_name == "linux":
            commands = []
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                commands.append(["loginctl", "lock-sessions"])
            commands.extend(
                (
                    ["loginctl", "lock-session"],
                    ["gnome-screensaver-command", "-l"],
                    ["xdg-screensaver", "lock"],
                )
            )
            for cmd in commands:
                r = subprocess.run(cmd, check=False, capture_output=True)
                if r.returncode == 0:
                    return
        elif os_name == "macos":
            subprocess.run(
                ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"],
                check=False,
                capture_output=True,
            )
        elif os_name == "windows":
            _lock_windows()
    except Exception:
        pass


def hostname() -> str:
    return platform.node() or "unknown"

"""OS-independent process matching and platform-specific enforcement."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import csv
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


_target_user = ""
_target_uid: int | None = None


def configure_target(user: str, identity: str) -> None:
    global _target_user, _target_uid
    _target_user = user
    _target_uid = int(identity) if identity.isdigit() else None


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


def _basename(value: str) -> str:
    value = value.strip()
    if value.endswith(" (deleted)"):
        value = value[: -len(" (deleted)")]
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    return value


def _linux_exe(pid: int) -> str:
    """Full executable path. `comm` is capped at 15 bytes by the kernel."""
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return ""


def _program_name(comm: str, argv0: str = "", exe: str = "") -> str:
    """Prefer the full program name when `ps` comm was truncated.

    A longer interpreter path must not replace a script's own comm name.
    Only a candidate that continues the truncated comm is used.
    """
    comm = _basename(comm)
    if len(comm) < 15:
        return comm
    for candidate in (_basename(exe), _basename(argv0)):
        if candidate.startswith(comm) and len(candidate) > len(comm):
            return candidate
    return comm


def _list_posix() -> list[RunningProcess]:
    # -ww: otherwise a narrow COLUMNS clips argv0 and the truncated comm cannot be repaired.
    try:
        out = subprocess.check_output(
            ["ps", "-ww", "-A", "-o", "pid=,uid=,comm=,args="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return []
    procs: list[RunningProcess] = []
    linux = detect_os() == "linux"
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            uid = int(parts[1])
        except ValueError:
            continue
        if _target_uid is not None and uid != _target_uid:
            continue
        argv0 = parts[3].split(None, 1)[0] if len(parts) > 3 else ""
        exe = _linux_exe(pid) if linux and len(parts[2]) >= 15 else ""
        name = _program_name(parts[2], argv0, exe)
        if not name:
            continue
        procs.append(RunningProcess(pid=pid, name=name))
    return procs


def _list_windows() -> list[RunningProcess]:
    try:
        out = subprocess.check_output(
            ["tasklist", "/V", "/FO", "CSV", "/NH"],
            text=True,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            errors="ignore",
            timeout=5,
        )
    except Exception:
        return []
    procs: list[RunningProcess] = []
    for row in csv.reader(out.splitlines()):
        if len(row) < 2 or not row[1].isdigit():
            continue
        if _target_user:
            owner = os.environ.get("COMPUTERNAME", "") + "\\" + _target_user
            if len(row) < 7 or row[6].casefold() != owner.casefold():
                continue
        procs.append(RunningProcess(pid=int(row[1]), name=row[0]))
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


def running_rule_ids(rules: list[dict]) -> list[int]:
    """Ids of quota rules whose process is running right now."""
    if not rules:
        return []
    hits: list[int] = []
    procs = list_processes()
    for rule in rules:
        try:
            rule_id = int(rule.get("id"))
        except (TypeError, ValueError):
            continue
        for proc in procs:
            if is_protected_process(proc.pid, proc.name):
                continue
            if matches_rule(proc.name, rule.get("pattern", ""), rule.get("match_mode", "contains")):
                hits.append(rule_id)
                break
    return hits


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


def user_session_active() -> bool:
    """True when a person is logged in. Failures keep enforcement on."""
    os_name = detect_os()
    if _target_user:
        if os_name == "linux":
            return _linux_desktop_session() is not None
        if os_name == "macos":
            return _macos_console_uid() == _target_uid
        if os_name == "windows":
            from kidscontrol_agent.account import windows_sessions
            return bool(windows_sessions(_target_user))
    try:
        if os_name == "linux":
            out = subprocess.check_output(
                ["loginctl", "list-sessions", "--no-legend"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return bool(out.strip())
        if os_name == "macos":
            out = subprocess.check_output(["who"], text=True, stderr=subprocess.DEVNULL, timeout=5)
            return bool(out.strip())
        if os_name == "windows":
            out = subprocess.check_output(
                ["query", "user"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
                encoding="utf-8",
                errors="ignore",
            )
            lowered = out.lower()
            return "active" in lowered or "aktiv" in lowered
    except Exception:
        return True
    return True


def notify(title: str, message: str, *, dry_run: bool = False, style: str | None = None) -> None:
    if dry_run:
        print(f"[notify] {title}: {message}")
        return
    from kidscontrol_agent.notify_style import load_notify_style, normalize_style

    chosen = normalize_style(style) or load_notify_style()
    os_name = detect_os()
    try:
        if _target_user and os_name == "macos" and _macos_console_uid() != _target_uid:
            return
        if _target_user and os_name == "linux" and _linux_desktop_session() is None:
            return
        if chosen == "window":
            _notify_window(os_name, title, message)
        else:
            _notify_toast(os_name, title, message)
    except Exception:
        pass


def _notify_env(title: str, message: str) -> dict[str, str]:
    return {"KC_TITLE": title, "KC_MESSAGE": message}


def _is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return False
    try:
        return geteuid() == 0
    except OSError:
        return False


_SESSION_USER_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


def _loginctl_props(session: str) -> dict[str, str] | None:
    if not _SESSION_ID_RE.fullmatch(session):
        return None
    try:
        out = subprocess.check_output(
            [
                "loginctl",
                "show-session",
                session,
                "-p",
                "Name",
                "-p",
                "User",
                "-p",
                "Active",
                "-p",
                "Display",
                "-p",
                "Type",
                "-p",
                "Remote",
                "-p",
                "State",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return None
    data: dict[str, str] = {}
    for line in out.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip()
    return data


def _linux_desktop_session() -> dict[str, str] | None:
    """Active local graphical login, when the agent is root and can see loginctl."""
    if not _is_root() or not shutil.which("loginctl"):
        return None
    try:
        listing = subprocess.check_output(
            ["loginctl", "list-sessions", "--no-legend"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return None
    for line in listing.splitlines():
        parts = line.split()
        if not parts:
            continue
        info = _loginctl_props(parts[0])
        if not info:
            continue
        if info.get("Active") != "yes" or info.get("Remote") == "yes":
            continue
        if info.get("Type") not in {"x11", "wayland", "mir"}:
            continue
        user = info.get("Name") or ""
        if _target_user and user != _target_user:
            continue
        uid = info.get("User") or ""
        if not uid.isdigit() or not _SESSION_USER_RE.fullmatch(user):
            continue
        return info
    return None


def _env_assignment(key: str, value: str) -> str:
    clean = str(value).replace("\n", " ").replace("\r", " ").replace("\0", "")
    return f"{key}={clean}"


def _linux_user_argv(argv: list[str], extra_env: dict[str, str] | None = None) -> list[str]:
    """Run a notifier in the logged-in user's session bus. Otherwise leave argv as-is."""
    info = _linux_desktop_session()
    if not info:
        return argv
    uid = info["User"]
    user = info["Name"]
    pairs = [
        _env_assignment("XDG_RUNTIME_DIR", f"/run/user/{uid}"),
        _env_assignment("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus"),
    ]
    display = info.get("Display") or ""
    if display:
        pairs.append(_env_assignment("DISPLAY", display))
    if info.get("Type") == "wayland":
        pairs.append(_env_assignment("WAYLAND_DISPLAY", "wayland-0"))
    for key, value in (extra_env or {}).items():
        pairs.append(_env_assignment(key, value))
    if shutil.which("runuser"):
        return ["runuser", "-u", user, "--", "env", *pairs, *argv]
    if shutil.which("sudo"):
        return ["sudo", "-n", "-u", user, "--", "env", *pairs, *argv]
    return argv


def _macos_console_uid() -> int | None:
    try:
        uid = os.stat("/dev/console").st_uid
    except OSError:
        return None
    if uid <= 0:
        return None
    return uid


def _macos_user_argv(argv: list[str]) -> list[str]:
    """Deliver a GUI command to the console user when the agent is root."""
    if not _is_root():
        return argv
    uid = _macos_console_uid()
    if not uid:
        return argv
    return ["launchctl", "asuser", str(uid), *argv]


def _windows_service_session() -> bool:
    """True when this process is not in the interactive console session (typical for SYSTEM)."""
    if detect_os() != "windows":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
        kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
        kernel32.GetCurrentProcessId.restype = wintypes.DWORD
        current = wintypes.DWORD()
        if not kernel32.ProcessIdToSessionId(kernel32.GetCurrentProcessId(), ctypes.byref(current)):
            return False
        active = kernel32.WTSGetActiveConsoleSessionId()
        if active == 0xFFFFFFFF:
            return False
        return current.value != active
    except Exception:
        return False


def _windows_env_block(extra: dict[str, str]):
    import ctypes

    merged = os.environ.copy()
    for key, value in extra.items():
        merged[str(key)] = str(value).replace("\0", "")
    items = []
    for key, value in merged.items():
        if not key or "=" in key or "\0" in key:
            continue
        items.append(f"{key}={value}")
    items.sort(key=str.upper)
    return ctypes.create_unicode_buffer("\0".join(items) + "\0\0")


def _windows_run_as_console_user(command_line: str, extra_env: dict[str, str] | None = None) -> bool:
    """Start a process in the active console session. Used from a SYSTEM service."""
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
    session_id = kernel32.WTSGetActiveConsoleSessionId()
    if _target_user:
        from kidscontrol_agent.account import windows_sessions
        sessions = windows_sessions(_target_user)
        if not sessions:
            return False
        session_id = session_id if session_id in sessions else sessions[0]
    if session_id == 0xFFFFFFFF:
        return False
    user_token = wintypes.HANDLE()
    wtsapi32.WTSQueryUserToken.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    wtsapi32.WTSQueryUserToken.restype = wintypes.BOOL
    if not wtsapi32.WTSQueryUserToken(session_id, ctypes.byref(user_token)):
        return False
    primary = wintypes.HANDLE()
    token_all_access = 0xF01FF
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    advapi32.DuplicateTokenEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                                        ctypes.c_int, ctypes.c_int, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.DuplicateTokenEx.restype = wintypes.BOOL
    if not advapi32.DuplicateTokenEx(user_token, token_all_access, None, 2, 1, ctypes.byref(primary)):
        kernel32.CloseHandle(user_token)
        return False

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
    command = ctypes.create_unicode_buffer(command_line)
    env_block = _windows_env_block(extra_env) if extra_env else None
    # CREATE_NO_WINDOW, plus CREATE_UNICODE_ENVIRONMENT when we pass a block.
    flags = 0x08000400 if env_block is not None else 0x08000000
    advapi32.CreateProcessAsUserW.argtypes = [
        wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION),
    ]
    advapi32.CreateProcessAsUserW.restype = wintypes.BOOL
    advapi32.CreateProcessAsUserW(
        primary,
        None,
        command,
        None,
        None,
        False,
        flags,
        env_block,
        None,
        ctypes.byref(info),
        ctypes.byref(process),
    )
    started = bool(process.hProcess)
    if process.hProcess:
        kernel32.CloseHandle(process.hProcess)
    if process.hThread:
        kernel32.CloseHandle(process.hThread)
    kernel32.CloseHandle(primary)
    kernel32.CloseHandle(user_token)
    return started


def _run_desktop(argv: list[str], *, extra_env: dict[str, str] | None = None) -> None:
    """Run a user-visible command. Root and SYSTEM target the interactive session."""
    os_name = detect_os()
    if os_name == "linux":
        _spawn_notice(_linux_user_argv(argv, extra_env))
        return
    if os_name == "macos":
        _spawn_notice(_macos_user_argv(argv))
        return
    if os_name == "windows":
        if _windows_service_session():
            _windows_run_as_console_user(subprocess.list2cmdline(argv), extra_env)
            return
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        _spawn_notice(argv, env=env)
        return
    _spawn_notice(argv)


_notice_processes: list[subprocess.Popen] = []


def _spawn_notice(argv: list[str], *, env: dict | None = None) -> None:
    """A child's response must never block enforcement; bound open windows."""
    _notice_processes[:] = [p for p in _notice_processes if p.poll() is None]
    if len(_notice_processes) >= 4:
        _notice_processes.pop(0).terminate()
    _notice_processes.append(subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, env=env,
    ))


def _notify_toast(os_name: str, title: str, message: str) -> None:
    if os_name == "linux":
        _run_desktop(["notify-send", "--", title, message])
        return
    if os_name == "macos":
        _run_desktop(
            [
                "osascript",
                "-e",
                "on run argv",
                "-e",
                "display notification (item 1 of argv) with title (item 2 of argv)",
                "-e",
                "end run",
                "--",
                message,
                title,
            ]
        )
        return
    if os_name == "windows":
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.Visible = $true; "
            "$n.ShowBalloonTip(8000, $env:KC_TITLE, $env:KC_MESSAGE, "
            "[System.Windows.Forms.ToolTipIcon]::Info); "
            "Start-Sleep -Seconds 6; $n.Dispose()"
        )
        _run_desktop(
            ["powershell", "-NoProfile", "-Command", ps],
            extra_env=_notify_env(title, message),
        )


def _notify_window(os_name: str, title: str, message: str) -> None:
    if os_name == "linux" and shutil.which("zenity"):
        _run_desktop(["zenity", "--warning", "--timeout=30", "--title", title, "--text", message])
        return
    if os_name == "macos":
        _run_desktop(
            [
                "osascript",
                "-e",
                "on run argv",
                "-e",
                "display dialog (item 1 of argv) with title (item 2 of argv) buttons {\"OK\"} default button 1 giving up after 30",
                "-e",
                "end run",
                "--",
                message,
                title,
            ]
        )
        return
    if os_name == "windows":
        ps = (
            "$shell = New-Object -ComObject WScript.Shell; "
            "$shell.Popup($env:KC_MESSAGE, 30, $env:KC_TITLE, 48)"
        )
        _run_desktop(
            ["powershell", "-NoProfile", "-Command", ps],
            extra_env=_notify_env(title, message),
        )
        return
    _tk_message(title, message)


def _tk_message(title: str, message: str) -> None:
    # A separate process keeps the modal Tk event loop out of the agent.
    _run_desktop([sys.executable, "-c",
        "import sys, tkinter as tk; from tkinter import messagebox; "
        "r=tk.Tk(); r.withdraw(); r.after(30000, r.destroy); "
        "messagebox.showwarning(sys.argv[1], sys.argv[2]); r.destroy()",
        title, message])


_MACOS_LOCK_SCREEN = (
    "/System/Library/CoreServices/RemoteManagement/AppleVNCServer.bundle/"
    "Contents/Support/LockScreen.app/Contents/MacOS/LockScreen"
)
_MACOS_CGSESSION = "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession"
_MACOS_LOGIN_FRAMEWORK = "/System/Library/PrivateFrameworks/login.framework/Versions/Current/login"


def _try_sac_lock() -> bool:
    """Lock via login.framework when the symbol exists. The old CGSession binary often does not."""
    if not os.path.exists(_MACOS_LOGIN_FRAMEWORK):
        return False
    try:
        import ctypes

        lib = ctypes.CDLL(_MACOS_LOGIN_FRAMEWORK)
        lock = lib.SACLockScreenImmediate
        lock.restype = None
        lock.argtypes = []
        lock()
        return True
    except Exception:
        return False


def _macos_lock_command() -> list[str]:
    """Prefer a real lock binary. Fall back to the Lock Screen shortcut in the GUI session."""
    if os.path.isfile(_MACOS_LOCK_SCREEN):
        return [_MACOS_LOCK_SCREEN]
    if os.path.isfile(_MACOS_CGSESSION):
        return [_MACOS_CGSESSION, "-suspend"]
    return [
        "osascript",
        "-e",
        'tell application "System Events" to key code 12 using {control down, command down}',
    ]


def _lock_macos() -> None:
    if _try_sac_lock():
        return
    subprocess.run(_macos_user_argv(_macos_lock_command()), check=False, capture_output=True)


def _lock_windows() -> None:
    """Lock the interactive desktop. From a SYSTEM service, start the lock in that session."""
    try:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=False, capture_output=True)
    except OSError:
        pass
    _windows_run_as_console_user("rundll32.exe user32.dll,LockWorkStation")


def lock_session(*, dry_run: bool = False) -> None:
    """Lock the interactive session when access is denied.

    The agent repeats this every few seconds while the hub (or the offline
    policy) still denies the session. A child who knows the password can
    unlock, but only until the next attempt. This is not a kiosk lock.
    """
    if dry_run:
        print("[lock] session lock requested")
        return
    os_name = detect_os()
    try:
        if os_name == "linux":
            commands = []
            if _is_root():
                commands.append(["loginctl", "lock-sessions"])
            commands.extend(
                (
                    ["loginctl", "lock-session"],
                    ["gnome-screensaver-command", "-l"],
                    ["xdg-screensaver", "lock"],
                )
            )
            for cmd in commands:
                try:
                    r = subprocess.run(cmd, check=False, capture_output=True)
                except OSError:
                    continue
                if r.returncode == 0:
                    return
        elif os_name == "macos":
            _lock_macos()
        elif os_name == "windows":
            _lock_windows()
    except Exception:
        pass


def hostname() -> str:
    return platform.node() or "unknown"

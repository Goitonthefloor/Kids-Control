"""Local child-account gate. Journal before changing OS state; never touch parents.

Only local, non-administrator accounts are supported. No password is changed.
The journal survives restarts and is also used by the administrator recovery CLI.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
from pathlib import Path

from kidscontrol_agent.enforce import detect_os


def _run(argv: list[str], *, env=None) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10, env=env)
    if result.returncode:
        raise RuntimeError(f"Kontoverwaltung fehlgeschlagen: {argv[0]} ({result.returncode})")
    return result.stdout.strip()


def _powershell(script: str, user: str) -> str:
    env = dict(os.environ, KC_ACCOUNT=user)
    return _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "$ErrorActionPreference='Stop'; " + script], env=env)


def inspect_account(user: str) -> dict:
    if not re.fullmatch(r"[\w][\w .@-]{0,63}", user, flags=re.UNICODE):
        raise ValueError("Lokalen Anmeldenamen des Kinderkontos angeben")
    system = detect_os()
    if system == "windows":
        data = json.loads(_powershell(
            "$u=Get-LocalUser -Name $env:KC_ACCOUNT; "
            "$admins=@(Get-LocalGroupMember -SID 'S-1-5-32-544'); "
            "@{id=$u.SID.Value; disabled=(!$u.Enabled); "
            "admin=(@($admins | Where-Object {$_.SID -eq $u.SID}).Count -gt 0)} | ConvertTo-Json -Compress", user))
        if data["admin"] or data["id"].endswith(("-500", "-501", "-503", "-504")):
            raise ValueError("Administrator-/Systemkonto darf kein Kinderkonto sein")
        return {"id": data["id"], "disabled": bool(data["disabled"])}
    import pwd
    import grp
    record = pwd.getpwnam(user)
    groups = {grp.getgrgid(gid).gr_name for gid in os.getgrouplist(user, record.pw_gid)}
    if record.pw_uid < (501 if system == "macos" else 1000) or groups & {"root", "sudo", "wheel", "admin"}:
        raise ValueError("Administrator-/Systemkonto darf kein Kinderkonto sein")
    if system == "linux":
        # Read only the expiration field; never persist or print password hashes.
        for line in Path("/etc/shadow").read_text().splitlines():
            fields = line.split(":")
            if fields[0] == user:
                return {"id": str(record.pw_uid), "expiry": fields[7]}
        raise ValueError("Nur lokale Konten mit /etc/shadow-Eintrag unterstützt")
    if system == "macos":
        raw = _run(["dscl", "-plist", "/Local/Default", "-read", f"/Users/{user}", "AuthenticationAuthority"])
        data = plistlib.loads(raw.encode())
        auth = data.get("dsAttrTypeStandard:AuthenticationAuthority", [])
        return {"id": str(record.pw_uid), "disabled": any(";DisabledUser;" in v for v in auth)}
    raise ValueError("Kontosperre auf diesem Betriebssystem nicht unterstützt")


def set_gate(user: str, state: dict) -> None:
    system = detect_os()
    if system == "windows":
        verb = "Disable" if state["disabled"] else "Enable"
        _powershell(f"Get-LocalUser -Name $env:KC_ACCOUNT | {verb}-LocalUser", user)
    elif system == "linux":
        _run(["usermod", "--expiredate", str(state["expiry"]), "--", user])
    elif system == "macos":
        _run(["pwpolicy", "-u", user, "-disableuser" if state["disabled"] else "-enableuser"])
    else:
        raise ValueError("Kontosperre nicht unterstützt")


def windows_sessions(user: str) -> list[int]:
    """Enumerate only the selected local account, including disconnected sessions."""
    import ctypes
    from ctypes import wintypes as w
    api = ctypes.WinDLL("wtsapi32", use_last_error=True)

    class Session(ctypes.Structure):
        _fields_ = [("id", w.DWORD), ("name", w.LPWSTR), ("state", ctypes.c_int)]

    pointer = ctypes.POINTER(Session)()
    count = w.DWORD()
    api.WTSEnumerateSessionsW.argtypes = [w.HANDLE, w.DWORD, w.DWORD, ctypes.POINTER(ctypes.POINTER(Session)), ctypes.POINTER(w.DWORD)]
    api.WTSEnumerateSessionsW.restype = w.BOOL
    api.WTSQuerySessionInformationW.argtypes = [w.HANDLE, w.DWORD, ctypes.c_int, ctypes.POINTER(w.LPWSTR), ctypes.POINTER(w.DWORD)]
    api.WTSQuerySessionInformationW.restype = w.BOOL
    api.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    if not api.WTSEnumerateSessionsW(None, 0, 1, ctypes.byref(pointer), ctypes.byref(count)):
        raise OSError(ctypes.get_last_error(), "WTSEnumerateSessionsW")

    def value(sid, kind):
        buffer, size = w.LPWSTR(), w.DWORD()
        if not api.WTSQuerySessionInformationW(None, sid, kind, ctypes.byref(buffer), ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), "WTSQuerySessionInformationW")
        try:
            return buffer.value or ""
        finally:
            api.WTSFreeMemory(buffer)

    try:
        return [pointer[i].id for i in range(count.value)
                if value(pointer[i].id, 5).casefold() == user.casefold()
                and value(pointer[i].id, 7).casefold() == os.environ.get("COMPUTERNAME", "").casefold()]
    finally:
        api.WTSFreeMemory(pointer)


def end_sessions(user: str, identity: str) -> None:
    system = detect_os()
    if system == "windows":
        import ctypes
        from ctypes import wintypes as w
        api = ctypes.WinDLL("wtsapi32", use_last_error=True)
        api.WTSLogoffSession.argtypes = [w.HANDLE, w.DWORD, w.BOOL]
        api.WTSLogoffSession.restype = w.BOOL
        for sid in windows_sessions(user):
            if not api.WTSLogoffSession(None, sid, False):
                raise OSError(ctypes.get_last_error(), "WTSLogoffSession")
    elif system == "linux":
        # No lock-sessions or global display-manager restart: only this UID.
        _run(["loginctl", "terminate-user", identity])
    elif system == "macos":
        # bootout also prevents GUI launch agents from restarting immediately.
        subprocess.run(["launchctl", "bootout", f"gui/{identity}"], capture_output=True, timeout=10)
        result = subprocess.run(["pkill", "-KILL", "-u", identity], capture_output=True, timeout=10)
        if result.returncode not in (0, 1):
            raise RuntimeError("Kinderprozesse konnten nicht beendet werden")


class AccountGate:
    def __init__(self, user: str, journal: Path):
        self.user, self.journal = user, journal
        self.identity = inspect_account(user)["id"]
        if journal.exists():
            saved = self._load()
            if saved["user"] != user or saved["original"]["id"] != self.identity:
                raise ValueError("Alte Kontosperre zuerst mit --restore-account zurücksetzen")

    def _load(self):
        return json.loads(self.journal.read_text(encoding="utf-8"))

    def _write(self, state):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.journal.with_suffix(".tmp")
        if temporary.is_symlink() or self.journal.is_symlink():
            raise PermissionError("Ungültiger Kontosperren-Pfad")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(state, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, self.journal)

    def apply(self, denied: bool, *, terminate: bool = True, dry_run: bool = False):
        current = inspect_account(self.user)
        if current["id"] != self.identity:
            raise ValueError("Kinderkonto wurde ersetzt; erneute Einrichtung erforderlich")
        if dry_run:
            return
        if denied:
            locked = {"id": self.identity, **({"expiry": "1"} if "expiry" in current else {"disabled": True})}
            if not self.journal.exists():
                self._write({"user": self.user, "original": current, "locked": locked})
            if current != locked:
                set_gate(self.user, locked)
                if inspect_account(self.user) != locked:
                    raise RuntimeError("Kontosperre konnte nicht bestätigt werden")
            if terminate:
                end_sessions(self.user, self.identity)
        elif self.journal.exists():
            saved = self._load()
            # Do not undo a subsequent administrator change to the same field.
            if current == saved["locked"] and current != saved["original"]:
                set_gate(self.user, saved["original"])
                if inspect_account(self.user) != saved["original"]:
                    raise RuntimeError("Kontofreigabe konnte nicht bestätigt werden")
            self.journal.unlink()

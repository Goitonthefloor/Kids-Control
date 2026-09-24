"""Where warning notices are shown: a message window or a toast."""

from __future__ import annotations

import os
from pathlib import Path

STYLES = ("window", "toast")

# The env file the running agent was started with (`--env`). Settings and
# notifications both read the choice from the sibling `notify-style` file.
_active_env: Path | None = None


def set_active_env(path: str | Path | None) -> None:
    global _active_env
    _active_env = Path(path) if path else None


def normalize_style(value: str | None) -> str | None:
    text = (value or "").strip().lower()
    if text in {"window", "message", "dialog", "fenster", "meldungsfenster"}:
        return "window"
    if text in {"toast", "balloon", "hinweis"}:
        return "toast"
    return None


def default_style() -> str:
    return "window" if os.name == "nt" else "toast"


def _unique(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _system_style_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        return Path(base) / "KidsControl" / "notify-style"
    return Path("/etc/kidscontrol/notify-style")


def _user_style_path() -> Path:
    return Path.home() / ".config" / "kidscontrol" / "notify-style"


def style_candidates() -> list[Path]:
    override = (os.getenv("KIDSCONTROL_NOTIFY_STYLE_PATH") or "").strip()
    paths: list[Path] = []
    if override:
        paths.append(Path(override))
    if _active_env is not None:
        paths.append(_active_env.parent / "notify-style")
    for candidate in (
        Path.cwd() / "client.env",
        Path("/etc/kidscontrol/client.env"),
        Path.home() / ".config" / "kidscontrol" / "client.env",
    ):
        if candidate.is_file():
            paths.append(candidate.parent / "notify-style")
            break
    paths.append(_system_style_path())
    paths.append(_user_style_path())
    return _unique(paths)


def _save_target() -> Path:
    override = (os.getenv("KIDSCONTROL_NOTIFY_STYLE_PATH") or "").strip()
    if override:
        return Path(override)
    if _active_env is not None:
        return _active_env.parent / "notify-style"
    for candidate in (
        Path.cwd() / "client.env",
        Path("/etc/kidscontrol/client.env"),
        Path.home() / ".config" / "kidscontrol" / "client.env",
    ):
        if candidate.is_file():
            return candidate.parent / "notify-style"
    system = _system_style_path()
    if _writable(system):
        return system
    return _user_style_path()


def load_notify_style() -> str:
    forced = normalize_style(os.getenv("KIDSCONTROL_NOTIFY_STYLE"))
    if forced:
        return forced
    for path in style_candidates():
        if not path.is_file():
            continue
        try:
            saved = normalize_style(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if saved:
            return saved
    return default_style()


def _writable(path: Path) -> bool:
    parent = path.parent
    if path.exists():
        return os.access(path, os.W_OK)
    return parent.exists() and os.access(parent, os.W_OK)


def save_notify_style(style: str) -> Path:
    chosen = normalize_style(style) or default_style()
    path = _save_target()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(chosen + "\n", encoding="utf-8")
    except OSError as exc:
        raise PermissionError(
            f"Keine Schreibrechte für {path}. "
            "Starte das Menü mit Administratorrechten, damit der Agent die Auswahl übernimmt."
        ) from exc
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path

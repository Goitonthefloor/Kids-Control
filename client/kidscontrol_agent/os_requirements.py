"""Install OS packages the agent needs, and prepare an SSH key for the controller."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def openssh_install_plan(os_name: str, available: set[str]) -> list[list[str]]:
    """Package-manager commands that install an OpenSSH server. Linux only."""
    if os_name != "linux":
        return []
    if "apt-get" in available:
        return [
            ["apt-get", "update"],
            ["apt-get", "install", "-y", "openssh-server"],
        ]
    if "dnf" in available:
        return [["dnf", "install", "-y", "openssh-server"]]
    if "pacman" in available:
        return [["pacman", "-Sy", "--noconfirm", "openssh"]]
    return []


def _which_names() -> set[str]:
    import shutil

    return {name for name in ("apt-get", "dnf", "pacman") if shutil.which(name)}


def install_openssh(*, os_name: str, dry_run: bool = False) -> list[str]:
    plan = openssh_install_plan(os_name, _which_names())
    if not plan:
        return []
    root = hasattr(os, "geteuid") and os.geteuid() == 0
    ran: list[str] = []
    for argv in plan:
        cmd = argv if root else ["sudo", *argv]
        ran.append(" ".join(cmd))
        if not dry_run:
            subprocess.run(cmd, check=False)
    if os_name == "linux":
        for unit in ("ssh", "sshd"):
            cmd = ["systemctl", "enable", "--now", unit]
            if not root:
                cmd = ["sudo", *cmd]
            ran.append(" ".join(cmd))
            if not dry_run:
                subprocess.run(cmd, check=False)
    return ran


def local_host_public_key() -> str:
    """OpenSSH host key the controller can pin. Empty when none is readable."""
    if os.name == "nt":
        return ""
    for name in ("ssh_host_ed25519_key.pub", "ssh_host_ecdsa_key.pub", "ssh_host_rsa_key.pub"):
        path = Path("/etc/ssh") / name
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text.startswith(("ssh-", "ecdsa-", "sk-")):
            return text
    return ""


def key_path() -> Path:
    return Path.home() / ".config" / "kidscontrol" / "ssh" / "id_ed25519"


def ensure_keypair(path: Path | None = None, *, dry_run: bool = False) -> tuple[str, str]:
    target = path or key_path()
    public = Path(str(target) + ".pub")
    if dry_run and not target.is_file():
        return "DRY-PRIVATE-KEY", "ssh-ed25519 DRY kidscontrol"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or not public.is_file():
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(target), "-C", "kidscontrol"],
            check=True,
        )
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    return target.read_text(encoding="utf-8"), public.read_text(encoding="utf-8")


def install_authorized_key(public_key: str, *, dry_run: bool = False) -> None:
    line = public_key.strip()
    if not line or dry_run:
        return
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(ssh_dir, 0o700)
    except OSError:
        pass
    auth = ssh_dir / "authorized_keys"
    existing = auth.read_text(encoding="utf-8") if auth.is_file() else ""
    if line not in existing:
        with auth.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(line + "\n")
    try:
        os.chmod(auth, 0o600)
    except OSError:
        pass

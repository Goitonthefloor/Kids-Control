"""Enroll this PC with the central KidsControl server."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from kidscontrol_agent.enforce import detect_os, hostname
from kidscontrol_agent.os_requirements import (
    ensure_keypair,
    install_authorized_key,
    install_openssh,
    local_host_public_key,
)
from kidscontrol_agent.service_install import ADMIN_NOTICE, install_system_service, is_privileged


def default_env_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("PROGRAMDATA") or str(Path.home())
        return Path(base) / "KidsControl" / "client.env"
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return Path("/etc/kidscontrol/client.env")
    return Path.home() / ".config" / "kidscontrol" / "client.env"


def _post(server: str, path: str, payload: dict) -> dict:
    url = server.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": f"KidsControl-Setup/{detect_os()}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        try:
            message = json.loads(detail).get("error") or detail
        except Exception:
            message = detail or exc.reason
        raise SystemExit(f"Server antwortet {exc.code}: {message}") from exc


def list_children(server: str, setup_password: str) -> list[dict]:
    body = _post(server, "/api/v1/setup/children", {"setup_password": setup_password})
    kids = body.get("children") or []
    return kids if isinstance(kids, list) else []


def post_progress(server: str, ticket: str, code: str, detail: str = "") -> None:
    payload = {"ticket": ticket, "code": code}
    if detail:
        payload["detail"] = " ".join(detail.split())[:180]
    try:
        _post(server, "/api/v1/setup/progress", payload)
    except SystemExit as exc:
        print(f"Hinweis: Meldung {code} konnte nicht gesendet werden ({exc}).")


def claim(
    server: str,
    ticket: str,
    *,
    os_name: str | None = None,
    host: str | None = None,
    ssh_private_key: str = "",
    ssh_user: str = "",
    ssh_host_key: str = "",
) -> dict:
    payload = {
        "ticket": ticket,
        "os": os_name or detect_os(),
        "hostname": host or hostname(),
        "ssh_private_key": ssh_private_key,
        "ssh_user": ssh_user or getpass.getuser(),
        "ssh_host_key": ssh_host_key,
    }
    return _post(server, "/api/v1/setup/claim", payload)


def enroll(
    server: str,
    setup_password: str = "",
    *,
    child_slug: str = "",
    device_name: str = "",
    token: str = "",
    os_name: str | None = None,
    host: str | None = None,
    ssh_private_key: str = "",
    ssh_user: str = "",
    ssh_host_key: str = "",
) -> dict:
    payload = {
        "setup_password": setup_password,
        "child_slug": child_slug,
        "device_name": device_name,
        "token": token,
        "os": os_name or detect_os(),
        "hostname": host or hostname(),
        "ssh_private_key": ssh_private_key,
        "ssh_user": ssh_user or getpass.getuser(),
        "ssh_host_key": ssh_host_key,
    }
    return _post(server, "/api/v1/setup/enroll", payload)


def write_client_env(path: Path, *, server: str, device_key: str, poll_seconds: int = 30) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        f"KIDSCONTROL_SERVER={server.rstrip('/')}\n"
        f"KIDSCONTROL_DEVICE_KEY={device_key}\n"
        f"KIDSCONTROL_POLL_SECONDS={int(poll_seconds)}\n"
    )
    path.write_text(text, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _interactive(args: argparse.Namespace) -> argparse.Namespace:
    if not args.server:
        args.server = input("Server-Adresse [http://127.0.0.1:8000]: ").strip() or "http://127.0.0.1:8000"
    if not args.token and not (args.setup_password and args.child):
        args.token = input("Einrichtungscode von der Kind-Seite: ").strip()
    if not args.token and not args.setup_password:
        args.setup_password = getpass.getpass("Client-Setup-Passwort: ")
    if not args.token and not args.child:
        kids = list_children(args.server, args.setup_password)
        if not kids:
            raise SystemExit("Am Server ist noch kein Kind angelegt. Bitte zuerst in der Eltern-UI ein Kind anlegen.")
        print("Kinder auf dem Server:")
        for kid in kids:
            print(f"  {kid.get('slug')}  {kid.get('display_name')}")
        args.child = input("Kurz-ID des Kindes: ").strip()
    if not args.device_name:
        default_name = hostname() or "Kinder-PC"
        args.device_name = input(f"Gerätename [{default_name}]: ").strip() or default_name
    return args


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KidsControl Client einrichten")
    parser.add_argument("--server", default="")
    parser.add_argument("--setup-password", default="")
    parser.add_argument("--child", default="", help="Kurz-ID des Kindes")
    parser.add_argument("--token", default="", help="Einrichtungscode von der Kind-Seite")
    parser.add_argument("--ticket", default="", help="Einrichtungsauftrag aus der Browser-Maske")
    parser.add_argument("--device-name", default="")
    parser.add_argument("--out", default="", help="Pfad für client.env")
    parser.add_argument("--skip-packages", action="store_true")
    args = parser.parse_args(argv)
    print()
    print("=" * 60)
    print("HINWEIS")
    print(ADMIN_NOTICE)
    print("=" * 60)
    print()
    if not is_privileged():
        print("Der Agent wird als Systemdienst eingerichtet, nicht unter dem Kinderkonto.", file=sys.stderr)
        print("Linux und macOS: sudo python3 -m kidscontrol_agent.setup …", file=sys.stderr)
        print("Windows: Eingabeaufforderung als Administrator öffnen.", file=sys.stderr)
        return 1
    ready = bool(args.server and (args.token or args.ticket or (args.setup_password and args.child)))
    if sys.stdin.isatty() and not ready:
        args = _interactive(args)
        ready = bool(args.server and (args.token or args.ticket or (args.setup_password and args.child)))
    if not ready:
        print(
            "Nicht-interaktiv: --server und --token (oder --setup-password und --child) sind nötig.",
            file=sys.stderr,
        )
        return 2
    if not args.device_name:
        args.device_name = hostname() or "PC"
    os_name = detect_os()
    if not args.skip_packages:
        for line in install_openssh(os_name=os_name, dry_run=False):
            print(f"[pkg] {line}")
    private_key = ""
    try:
        private_key, public_key = ensure_keypair()
        install_authorized_key(public_key)
    except Exception as exc:
        print(f"SSH-Schlüssel konnte nicht erzeugt werden: {exc}", file=sys.stderr)
    try:
        if args.ticket:
            result = claim(
                args.server,
                args.ticket,
                ssh_private_key=private_key,
                ssh_user=getpass.getuser(),
                ssh_host_key=local_host_public_key(),
            )
            post_progress(args.server, args.ticket, "identity_sent")
        else:
            result = enroll(
                args.server,
                args.setup_password,
                child_slug=args.child,
                device_name=args.device_name,
                token=args.token,
                ssh_private_key=private_key,
                ssh_user=getpass.getuser(),
                ssh_host_key=local_host_public_key(),
            )
    except SystemExit as exc:
        if args.ticket:
            post_progress(args.server, args.ticket, "failed", detail=str(exc))
        raise
    out = Path(args.out) if args.out else default_env_path()
    write_client_env(
        out,
        server=args.server,
        device_key=result["device_key"],
        poll_seconds=int(result.get("poll_interval_seconds") or 30),
    )
    child = (result.get("child") or {}).get("display_name") or args.child
    print(f"Gerät für {child} eingerichtet.")
    print(f"Konfiguration: {out}")
    try:
        status = install_system_service(out)
    except Exception as exc:
        print(f"Systemdienst konnte nicht gestartet werden: {exc}", file=sys.stderr)
        if args.ticket:
            post_progress(args.server, args.ticket, "failed", detail=str(exc))
        return 1
    print(status)
    if args.ticket:
        post_progress(args.server, args.ticket, "service_started")
        post_progress(args.server, args.ticket, "finished")
        print(f"Fertig. {child} ist auf diesem PC eingerichtet.")
    print("Das Kinderkonto darf kein Administrator sein, sonst kann es den Dienst beenden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

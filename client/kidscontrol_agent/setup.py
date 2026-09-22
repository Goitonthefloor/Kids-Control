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


def enroll(
    server: str,
    setup_password: str,
    *,
    child_slug: str,
    device_name: str,
    os_name: str | None = None,
    host: str | None = None,
) -> dict:
    return _post(
        server,
        "/api/v1/setup/enroll",
        {
            "setup_password": setup_password,
            "child_slug": child_slug,
            "device_name": device_name,
            "os": os_name or detect_os(),
            "hostname": host or hostname(),
        },
    )


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
    if not args.setup_password:
        args.setup_password = getpass.getpass("Client-Setup-Passwort: ")
    if not args.child:
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
    parser.add_argument("--device-name", default="")
    parser.add_argument("--out", default="", help="Pfad für client.env")
    args = parser.parse_args(argv)
    if sys.stdin.isatty() and not (args.server and args.setup_password and args.child and args.device_name):
        args = _interactive(args)
    if not (args.server and args.setup_password and args.child and args.device_name):
        print(
            "Nicht-interaktiv: --server, --setup-password, --child und --device-name sind nötig.",
            file=sys.stderr,
        )
        return 2
    result = enroll(
        args.server,
        args.setup_password,
        child_slug=args.child,
        device_name=args.device_name,
    )
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
    print(f"Start: python -m kidscontrol_agent --env {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

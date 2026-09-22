"""First-run server setup. Writes data/server.env."""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

from app import config
from app.i18n import normalize_lang, t

MIN_PASSWORD = 8


class SetupError(Exception):
    pass


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def validate_passwords(*, admin_password: str, setup_password: str) -> None:
    if any(ch in admin_password + setup_password for ch in "\n\r"):
        raise SetupError("err_password_newline")
    if len(admin_password) < MIN_PASSWORD:
        raise SetupError("err_admin_short")
    if len(setup_password) < MIN_PASSWORD:
        raise SetupError("err_setup_short")
    if admin_password == setup_password:
        raise SetupError("err_passwords_same")


def write_server_env(
    *,
    admin_user: str,
    admin_password: str,
    setup_password: str,
    timezone_name: str,
    host: str,
    port: int,
    secret: str,
    path: Path | None = None,
) -> Path:
    target = path or config.server_env_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"KIDSCONTROL_ADMIN_USER={_quote(admin_user)}",
        f"KIDSCONTROL_ADMIN_PASSWORD={_quote(admin_password)}",
        f"KIDSCONTROL_SETUP_PASSWORD={_quote(setup_password)}",
        f"KIDSCONTROL_SECRET={_quote(secret)}",
        f"KIDSCONTROL_TZ={_quote(timezone_name)}",
        f"HOST={_quote(host)}",
        f"PORT={port}",
        "KIDSCONTROL_AGENT_POLL_SECONDS=30",
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    os.environ["KIDSCONTROL_ADMIN_USER"] = admin_user
    os.environ["KIDSCONTROL_ADMIN_PASSWORD"] = admin_password
    os.environ["KIDSCONTROL_SETUP_PASSWORD"] = setup_password
    os.environ["KIDSCONTROL_SECRET"] = secret
    os.environ["KIDSCONTROL_TZ"] = timezone_name
    os.environ["HOST"] = host
    os.environ["PORT"] = str(port)
    return target


def apply_setup(
    *,
    admin_user: str,
    admin_password: str,
    setup_password: str,
    timezone_name: str = "Europe/Berlin",
    host: str = "0.0.0.0",
    port: int = 8000,
    force: bool = False,
) -> Path:
    admin_user = admin_user.strip() or "admin"
    if config.is_configured() and not force:
        raise SetupError("err_already_configured")
    validate_passwords(admin_password=admin_password, setup_password=setup_password)
    current_secret = config.secret()
    if not current_secret or current_secret == "dev-secret-change-me":
        current_secret = secrets.token_urlsafe(32)
    return write_server_env(
        admin_user=admin_user,
        admin_password=admin_password,
        setup_password=setup_password,
        timezone_name=timezone_name.strip() or "Europe/Berlin",
        host=host.strip() or "0.0.0.0",
        port=int(port),
        secret=current_secret,
    )


def _prompt(args: argparse.Namespace) -> argparse.Namespace:
    if not args.admin_user:
        args.admin_user = input("Eltern-Benutzername [admin]: ").strip() or "admin"
    if not args.admin_password:
        args.admin_password = getpass.getpass("Eltern-Passwort: ")
        again = getpass.getpass("Eltern-Passwort wiederholen: ")
        if args.admin_password != again:
            raise SetupError("passwords_mismatch_admin")
    if not args.setup_password:
        args.setup_password = getpass.getpass("Client-Setup-Passwort: ")
        again = getpass.getpass("Client-Setup-Passwort wiederholen: ")
        if args.setup_password != again:
            raise SetupError("passwords_mismatch_setup")
    return args


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KidsControl Server einrichten")
    parser.add_argument("--admin-user", default="")
    parser.add_argument("--admin-password", default="")
    parser.add_argument("--setup-password", default="")
    parser.add_argument("--timezone", default="Europe/Berlin")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if sys.stdin.isatty():
            args = _prompt(args)
        elif not (args.admin_password and args.setup_password):
            raise SetupError("err_setup_short")
        path = apply_setup(
            admin_user=args.admin_user or "admin",
            admin_password=args.admin_password,
            setup_password=args.setup_password,
            timezone_name=args.timezone,
            host=args.host,
            port=args.port,
            force=args.force,
        )
    except SetupError as exc:
        lang = normalize_lang(os.environ.get("LANG"))
        print(t(lang, str(exc)), file=sys.stderr)
        return 2
    print(f"Server eingerichtet. Konfiguration: {path}")
    print("Starte danach: python -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
    print("Das Client-Setup-Passwort wird auf jedem Kinder-PC beim Einrichten abgefragt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

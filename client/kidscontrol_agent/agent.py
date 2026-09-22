"""KidsControl agent: poll central hub and enforce session + app rules."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from kidscontrol_agent.config import load_config
from kidscontrol_agent.enforce import (
    detect_os,
    find_matching_pids,
    hostname,
    kill_pid,
    lock_session,
    notify,
)


def sync(server: str, device_key: str, *, active: bool = True) -> dict:
    url = f"{server}/api/v1/agent/sync"
    payload = json.dumps(
        {
            "active": active,
            "hostname": hostname(),
            "os": detect_os(),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Device-Key": device_key,
            "User-Agent": f"KidsControl-Agent/{detect_os()}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def enforce_policy(policy: dict, *, dry_run: bool = False) -> None:
    allow = bool(policy.get("allow_session"))
    reason = policy.get("reason_label") or policy.get("reason") or ""
    actions = policy.get("actions") or {}

    if not allow and actions.get("lock_session_when_denied", True):
        notify("KidsControl", f"Zeit abgelaufen: {reason}", dry_run=dry_run)
        lock_session(dry_run=dry_run)

    if actions.get("kill_blocked_apps", True):
        rules = policy.get("blocked_apps") or []
        if rules:
            for pid, name, label in find_matching_pids(rules):
                print(f"[block] killing pid={pid} name={name} rule={label}")
                kill_pid(pid, dry_run=dry_run)
                notify("KidsControl", f"App gesperrt: {label or name}", dry_run=dry_run)

    if allow and policy.get("warn"):
        rem = policy.get("remaining_minutes")
        if rem is not None:
            notify("KidsControl", f"Noch ca. {rem} Minuten", dry_run=dry_run)


def run_once(cfg: dict) -> int:
    if not cfg["device_key"]:
        print("Fehler: KIDSCONTROL_DEVICE_KEY fehlt.", file=sys.stderr)
        return 2
    try:
        policy = sync(cfg["server"], cfg["device_key"], active=True)
    except urllib.error.HTTPError as exc:
        print(f"HTTP-Fehler {exc.code}: {exc.read().decode('utf-8', errors='ignore')}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Sync fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    child = (policy.get("child") or {}).get("display_name") or "?"
    status = "ALLOW" if policy.get("allow_session") else "DENY"
    print(
        f"[{status}] {child} reason={policy.get('reason')} "
        f"remaining={policy.get('remaining_minutes')} "
        f"blocked_apps={len(policy.get('blocked_apps') or [])}"
    )
    enforce_policy(policy, dry_run=cfg["dry_run"])
    return 0


def run_loop(cfg: dict) -> int:
    print(f"KidsControl Agent startet → {cfg['server']} (OS={detect_os()}, dry_run={cfg['dry_run']})")
    while True:
        code = run_once(cfg)
        # On auth errors, back off longer
        sleep_for = cfg["poll_seconds"] if code != 2 else 60
        try:
            # Prefer server-suggested interval when available
            time.sleep(sleep_for)
        except KeyboardInterrupt:
            print("Beendet.")
            return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env_path = None
    once = False
    for i, arg in enumerate(argv):
        if arg == "--env" and i + 1 < len(argv):
            env_path = argv[i + 1]
        if arg == "--once":
            once = True
    cfg = load_config(env_path)
    if once:
        return run_once(cfg)
    return run_loop(cfg)


if __name__ == "__main__":
    raise SystemExit(main())

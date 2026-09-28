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
    running_rule_ids,
    user_session_active,
)
from kidscontrol_agent.inventory import (
    cached_pending_updates,
    load_cached_quota,
    load_cached_watches,
    query_versions,
    refresh_pending_updates,
    run_update,
    save_cached_quota,
    save_cached_watches,
)
from kidscontrol_agent.notify_style import set_active_env
from kidscontrol_agent.offline import offline_policy, save_cached_policy
from kidscontrol_agent.quota_warn import warn_running_quotas

# While the hub says the session is denied, lock again on this cadence.
# The poll interval stays longer; this only shortens the unlocked gap.
LOCK_RETRY_SECONDS = 5


def sync(server: str, device_key: str, *, active: bool = True) -> dict:
    url = f"{server}/api/v1/agent/sync"
    watches = load_cached_watches()
    body = {
        "active": active,
        "hostname": hostname(),
        "os": detect_os(),
        "inventory": query_versions(watches) if watches else [],
        "running_apps": running_rule_ids(load_cached_quota()),
    }
    pending = cached_pending_updates()
    if pending is not None:
        body["pending_updates"] = pending
    payload = json.dumps(body).encode("utf-8")
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


def enforce_policy(policy: dict, *, dry_run: bool = False, announce: bool = True) -> None:
    allow = bool(policy.get("allow_session"))
    reason = policy.get("reason_label") or policy.get("reason") or ""
    actions = policy.get("actions") or {}

    if not allow and actions.get("lock_session_when_denied", True):
        if announce:
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


def report_command(server: str, device_key: str, command_id: int, status: str, output: str) -> None:
    url = f"{server}/api/v1/agent/commands/{command_id}/result"
    payload = json.dumps({"status": status, "output": output}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Device-Key": device_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def handle_commands(cfg: dict, policy: dict) -> None:
    watches = policy.get("watch_packages") or []
    if isinstance(watches, list):
        save_cached_watches([str(x) for x in watches])
    for cmd in policy.get("commands") or []:
        kind = cmd.get("kind")
        package = cmd.get("package_name")
        cid = cmd.get("id")
        if kind not in {"update_one", "update_all"} or cid is None:
            continue
        print(f"[update] command={cid} kind={kind} package={package}")
        try:
            report_command(cfg["server"], cfg["device_key"], int(cid), "running", "")
        except Exception as exc:
            print(f"Start-Meldung fehlgeschlagen: {exc}", file=sys.stderr)
        status, output = run_update(package if kind == "update_one" else None, dry_run=cfg["dry_run"])
        try:
            report_command(cfg["server"], cfg["device_key"], int(cid), status, output)
        except Exception as exc:
            print(f"Ergebnis-Meldung fehlgeschlagen: {exc}", file=sys.stderr)


def _describe(policy: dict) -> None:
    child = (policy.get("child") or {}).get("display_name") or "?"
    status = "ALLOW" if policy.get("allow_session") else "DENY"
    print(
        f"[{status}] {child} reason={policy.get('reason')} "
        f"remaining={policy.get('remaining_minutes')} "
        f"blocked_apps={len(policy.get('blocked_apps') or [])}"
    )


def _apply_offline(cfg: dict) -> tuple[int, bool, dict]:
    """Hub unreachable: lock and keep enforcing the cached deny rules."""
    policy = offline_policy()
    _describe(policy)
    enforce_policy(policy, dry_run=cfg["dry_run"])
    return 1, True, policy


def run_cycle(cfg: dict) -> tuple[int, bool, dict | None]:
    """One poll. Returns (exit code, session denied, policy to keep enforcing)."""
    if not cfg["device_key"]:
        print("Fehler: KIDSCONTROL_DEVICE_KEY fehlt.", file=sys.stderr)
        return 2, False, None
    try:
        policy = sync(cfg["server"], cfg["device_key"], active=user_session_active())
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            detail = ""
        print(f"HTTP-Fehler {exc.code}: {detail}", file=sys.stderr)
        return _apply_offline(cfg)
    except Exception as exc:
        print(f"Sync fehlgeschlagen: {exc}", file=sys.stderr)
        return _apply_offline(cfg)

    save_cached_policy(policy)
    _describe(policy)
    save_cached_quota(policy.get("quota_apps") or [])
    warn_running_quotas(policy.get("quota_apps") or [], dry_run=cfg["dry_run"])
    enforce_policy(policy, dry_run=cfg["dry_run"])
    handle_commands(cfg, policy)
    refresh_pending_updates()
    denied = not bool(policy.get("allow_session"))
    return 0, denied, policy if denied else None


def run_once(cfg: dict) -> int:
    code, _denied, _policy = run_cycle(cfg)
    return code


def _wait_until_next_sync(
    seconds: int,
    *,
    policy: dict | None,
    session_denied: bool,
    dry_run: bool,
) -> None:
    """Sleep until the next poll. While denied, lock and stop apps again every few seconds."""
    if seconds <= 0:
        return
    if not session_denied or dry_run or not policy:
        time.sleep(seconds)
        return
    remaining = seconds
    while remaining > 0:
        chunk = min(LOCK_RETRY_SECONDS, remaining)
        time.sleep(chunk)
        remaining -= chunk
        if remaining > 0:
            enforce_policy(policy, dry_run=False, announce=False)


def run_loop(cfg: dict) -> int:
    print(f"KidsControl Agent startet → {cfg['server']} (OS={detect_os()}, dry_run={cfg['dry_run']})")
    while True:
        code, denied, policy = run_cycle(cfg)
        # Missing device key is a local config error; back off longer.
        sleep_for = cfg["poll_seconds"] if code != 2 else 60
        try:
            _wait_until_next_sync(
                sleep_for,
                policy=policy,
                session_denied=denied,
                dry_run=cfg["dry_run"],
            )
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
    set_active_env(env_path)
    if "--settings" in argv:
        from kidscontrol_agent.settings import open_settings

        return open_settings()
    cfg = load_config(env_path)
    if once:
        return run_once(cfg)
    return run_loop(cfg)


if __name__ == "__main__":
    raise SystemExit(main())

"""KidsControl agent: poll central hub and enforce session + app rules."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

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
    configure_target,
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
APP_CLOSE_WARNING_SECONDS = 30
_app_deadlines: dict[str, float] = {}
_inventory: list[dict] = []


def sync(server: str, device_key: str, *, active: bool = True) -> dict:
    url = f"{server}/api/v1/agent/sync"
    body = {
        "active": active,
        "hostname": hostname(),
        "os": detect_os(),
        "inventory": list(_inventory),
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


def enforce_policy(policy: dict, *, dry_run: bool = False, announce: bool = True, account_gate=None) -> None:
    allow = bool(policy.get("allow_session"))
    reason = policy.get("reason_label") or policy.get("reason") or ""
    actions = policy.get("actions") or {}

    if account_gate is not None:
        account_gate.enforce(allow, dry_run=dry_run)
    elif not allow and actions.get("lock_session_when_denied", True):
        lock_session(dry_run=dry_run)
        if announce:
            notify("KidsControl", f"Zeit abgelaufen: {reason}", dry_run=dry_run)

    if actions.get("kill_blocked_apps", True):
        rules = policy.get("blocked_apps") or []
        live_labels = {r.get("label") or r.get("pattern") or "" for r in rules}
        for label in list(_app_deadlines):
            if label not in live_labels:
                _app_deadlines.pop(label)
        if rules:
            for pid, name, label in find_matching_pids(rules):
                # Keep the deadline across process restarts. Reopening the app
                # cannot repeatedly buy another warning period.
                if label not in _app_deadlines:
                    _app_deadlines[label] = time.monotonic() + APP_CLOSE_WARNING_SECONDS
                    notify("KidsControl", f"{label or name} wird in 30 Sekunden geschlossen. Bitte jetzt speichern.", dry_run=dry_run)
                if time.monotonic() < _app_deadlines[label]:
                    continue
                print(f"[block] killing pid={pid} name={name} rule={label}")
                kill_pid(pid, dry_run=dry_run)

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


def run_cycle(cfg: dict, *, apply: bool = True) -> tuple[int, bool, dict | None]:
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
        if apply:
            return _apply_offline(cfg)
        return 1, True, offline_policy()
    except Exception as exc:
        print(f"Sync fehlgeschlagen: {exc}", file=sys.stderr)
        if apply:
            return _apply_offline(cfg)
        return 1, True, offline_policy()

    save_cached_policy(policy)
    _describe(policy)
    save_cached_quota(policy.get("quota_apps") or [])
    if apply:
        warn_running_quotas(policy.get("quota_apps") or [], dry_run=cfg["dry_run"])
        enforce_policy(policy, dry_run=cfg["dry_run"])
    denied = not bool(policy.get("allow_session"))
    return 0, denied, policy


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
    if not cfg["device_key"]:
        return 2
    gate = ManagedSession(cfg)
    # Neither HTTP timeouts nor package managers run on the enforcement thread.
    poller = ThreadPoolExecutor(max_workers=1, thread_name_prefix="policy")
    maintenance = ThreadPoolExecutor(max_workers=1, thread_name_prefix="updates")
    worker = Maintenance()
    fetch = poller.submit(run_cycle, cfg, apply=False)
    update = None
    current = offline_policy()
    next_poll = time.monotonic()
    fresh_at = None
    try:
        while True:
            now = time.monotonic()
            if fetch is not None and fetch.done():
                try:
                    code, _denied, policy = fetch.result()
                    current = policy or offline_policy()
                    fresh_at = now if code == 0 else None
                    warn_running_quotas(current.get("quota_apps") or [], dry_run=cfg["dry_run"])
                except Exception as exc:
                    print(f"Policy fehlgeschlagen: {exc}", file=sys.stderr)
                    current, fresh_at = offline_policy(), None
                fetch = None
                next_poll = now + cfg["poll_seconds"]
            if fresh_at is not None and now - fresh_at > cfg["poll_seconds"] + 20:
                current, fresh_at = offline_policy(), None
            if fetch is None and now >= next_poll:
                fetch = poller.submit(run_cycle, cfg, apply=False)
            if fresh_at is not None and (update is None or update.done()):
                if update is not None:
                    try:
                        update.result()
                    except Exception as exc:
                        print(f"Wartung fehlgeschlagen: {exc}", file=sys.stderr)
                update = maintenance.submit(worker.run, cfg, current)
            try:
                enforce_policy(current, dry_run=cfg["dry_run"], announce=False, account_gate=gate)
            except Exception as exc:
                print(f"Durchsetzung fehlgeschlagen: {exc}", file=sys.stderr)
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        poller.shutdown(wait=False, cancel_futures=True)
        maintenance.shutdown(wait=False, cancel_futures=True)


class ManagedSession:
    """Block authentication immediately; warn before ending the child's session."""

    def __init__(self, cfg):
        from kidscontrol_agent.account import AccountGate
        if not cfg.get("account"):
            raise ValueError("Kinderkonto fehlt. Einrichtung erneut mit --account ANMELDENAME ausführen.")
        self.gate = AccountGate(cfg["account"], Path(cfg["account_journal"]))
        configure_target(cfg["account"], self.gate.identity)
        self.deadline = None
        self.next_check = 0.0

    def enforce(self, allow: bool, *, dry_run: bool):
        now = time.monotonic()
        if allow:
            if self.deadline is not None or self.gate.journal.exists():
                self.gate.apply(False, dry_run=dry_run)
            self.deadline = None
            self.next_check = 0.0
            return
        if self.deadline is None:
            self.deadline = now + APP_CLOSE_WARNING_SECONDS
            notify("KidsControl", "Deine Sitzung endet in 30 Sekunden. Bitte speichern. Eine neue Anmeldung ist bis zur Freigabe gesperrt.", dry_run=dry_run)
        if now >= self.next_check:
            self.gate.apply(True, terminate=now >= self.deadline, dry_run=dry_run)
            self.next_check = now + 5


class Maintenance:
    """One serial update worker, with retryable result delivery and inventory."""

    def __init__(self):
        self.results: dict[int, tuple[str, str]] = {}
        self.reported: set[int] = set()
        self.next_inventory = 0.0

    def run(self, cfg: dict, policy: dict) -> None:
        global _inventory
        watches = policy.get("watch_packages") or []
        save_cached_watches([str(x) for x in watches])
        for command in policy.get("commands") or []:
            cid = int(command["id"])
            if cid in self.results or cid in self.reported:
                continue
            if command.get("kind") not in {"update_one", "update_all"}:
                continue
            # Do not execute until the hub has acknowledged ownership.
            report_command(cfg["server"], cfg["device_key"], cid, "running", "")
            self.results[cid] = run_update(
                command.get("package_name") if command["kind"] == "update_one" else None,
                dry_run=cfg["dry_run"],
            )
        for cid, (status, output) in list(self.results.items()):
            report_command(cfg["server"], cfg["device_key"], cid, status, output)
            self.reported.add(cid)
            del self.results[cid]
        if time.monotonic() >= self.next_inventory:
            _inventory = query_versions(watches) if watches else []
            refresh_pending_updates()
            self.next_inventory = time.monotonic() + 60


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
    if "--restore-account" in argv:
        from kidscontrol_agent.account import AccountGate
        from kidscontrol_agent.service_install import is_privileged
        if not is_privileged():
            raise PermissionError("Kontofreigabe erfordert Administratorrechte")
        AccountGate(cfg["account"], Path(cfg["account_journal"])).apply(False)
        return 0
    if once:
        gate = ManagedSession(cfg)
        code, _denied, policy = run_cycle(cfg, apply=False)
        if policy:
            enforce_policy(policy, dry_run=cfg["dry_run"], account_gate=gate)
        return code
    return run_loop(cfg)


if __name__ == "__main__":
    raise SystemExit(main())

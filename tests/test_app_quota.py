"""Quota programs reported by the agent."""

from kidscontrol_agent.enforce import RunningProcess, running_rule_ids


def test_running_rule_ids_match_process_names(monkeypatch):
    monkeypatch.setattr(
        "kidscontrol_agent.enforce.list_processes",
        lambda: [RunningProcess(pid=20, name="javaw.exe"), RunningProcess(pid=1, name="systemd")],
    )
    monkeypatch.setattr("kidscontrol_agent.enforce.is_protected_process", lambda pid, name: pid <= 1)
    rules = [
        {"id": 4, "pattern": "javaw", "match_mode": "contains"},
        {"id": 5, "pattern": "notepad", "match_mode": "exact"},
        {"id": "nope", "pattern": "javaw", "match_mode": "contains"},
    ]
    assert running_rule_ids(rules) == [4]

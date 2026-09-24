"""Quota warnings at 5, 2, and 1 minute for a running program."""

from kidscontrol_agent import quota_warn
from kidscontrol_agent.quota_warn import quota_warning, quota_warning_text, warn_running_quotas


def test_warning_levels_fire_once_each():
    assert quota_warning(6 * 60, set()) is None
    assert quota_warning(5 * 60, set()) == (5, 5)
    assert quota_warning(4 * 60, {5}) is None
    assert quota_warning(3 * 60, set()) == (5, 3)
    assert quota_warning(2 * 60, {5}) == (2, 2)
    assert quota_warning(60, {5, 2}) == (1, 1)
    assert quota_warning(30, {5, 2, 1}) is None
    assert quota_warning(0, set()) is None
    assert quota_warning_text("Minecraft", 1) == "Minecraft: noch 1 Minute"
    assert quota_warning_text("Minecraft", 5) == "Minecraft: noch 5 Minuten"


def test_running_program_warns_at_each_step_and_not_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(quota_warn, "WARN_CACHE", tmp_path / "quota_warnings.json")
    notes: list[str] = []
    monkeypatch.setattr(quota_warn, "notify", lambda title, message, dry_run=False: notes.append(message))
    monkeypatch.setattr(quota_warn, "running_rule_ids", lambda rules: [7])
    app = {"id": 7, "label": "Minecraft", "pattern": "minecraft", "match_mode": "contains"}

    assert warn_running_quotas([{**app, "remaining_seconds": 300}]) == ["Minecraft: noch 5 Minuten"]
    assert warn_running_quotas([{**app, "remaining_seconds": 240}]) == []
    assert warn_running_quotas([{**app, "remaining_seconds": 120}]) == ["Minecraft: noch 2 Minuten"]
    assert warn_running_quotas([{**app, "remaining_seconds": 60}]) == ["Minecraft: noch 1 Minute"]
    assert warn_running_quotas([{**app, "remaining_seconds": 40}]) == []
    assert notes == [
        "Minecraft: noch 5 Minuten",
        "Minecraft: noch 2 Minuten",
        "Minecraft: noch 1 Minute",
    ]


def test_idle_program_does_not_warn(tmp_path, monkeypatch):
    monkeypatch.setattr(quota_warn, "WARN_CACHE", tmp_path / "quota_warnings.json")
    monkeypatch.setattr(quota_warn, "notify", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("notify")))
    monkeypatch.setattr(quota_warn, "running_rule_ids", lambda rules: [])
    assert warn_running_quotas([{"id": 7, "label": "Minecraft", "remaining_seconds": 120}]) == []


def test_new_day_clears_warnings(tmp_path, monkeypatch):
    monkeypatch.setattr(quota_warn, "WARN_CACHE", tmp_path / "quota_warnings.json")
    notes: list[str] = []
    monkeypatch.setattr(quota_warn, "notify", lambda title, message, dry_run=False: notes.append(message))
    monkeypatch.setattr(quota_warn, "running_rule_ids", lambda rules: [7])
    app = {"id": 7, "label": "Minecraft", "pattern": "minecraft", "match_mode": "contains"}
    warn_running_quotas([{**app, "remaining_seconds": 60}])
    assert warn_running_quotas([{**app, "remaining_seconds": 10 * 60}]) == []
    assert warn_running_quotas([{**app, "remaining_seconds": 300}]) == ["Minecraft: noch 5 Minuten"]

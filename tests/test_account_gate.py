"""Only fake account backends are used; never modify the test runner's users."""
import json
import pytest
from kidscontrol_agent import account, agent


@pytest.fixture
def backend(monkeypatch):
    state = {"id": "1001", "expiry": ""}
    changes, ended = [], []
    monkeypatch.setattr(account, "inspect_account", lambda user: dict(state))
    def change(user, value):
        changes.append((user, value.copy()))
        state.update(value)
    monkeypatch.setattr(account, "set_gate", change)
    monkeypatch.setattr(account, "end_sessions", lambda user, uid: ended.append((user, uid)))
    return state, changes, ended


def test_restart_restores_only_child_original_state(tmp_path, backend):
    state, changes, ended = backend
    path = tmp_path / "lock.json"
    gate = account.AccountGate("mia", path)
    gate.apply(True, terminate=False)
    assert state["expiry"] == "1" and not ended
    assert json.loads(path.read_text())["original"]["expiry"] == ""
    account.AccountGate("mia", path).apply(True)
    assert ended == [("mia", "1001")]
    account.AccountGate("mia", path).apply(False)
    assert state["expiry"] == "" and not path.exists()
    assert all(user == "mia" for user, _ in changes)


@pytest.mark.parametrize("initial", [{"id": "S-test", "disabled": True}, {"id": "1001", "expiry": "1"}])
def test_preexisting_disabled_account_is_never_enabled(tmp_path, backend, initial):
    state, changes, ended = backend
    state.clear(); state.update(initial)
    gate = account.AccountGate("mia", tmp_path / "lock.json")
    gate.apply(True); gate.apply(False)
    assert state == initial and not changes


def test_journal_failure_prevents_any_mutation(tmp_path, backend, monkeypatch):
    state, changes, ended = backend
    gate = account.AccountGate("mia", tmp_path / "lock.json")
    monkeypatch.setattr(gate, "_write", lambda value: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        gate.apply(True)
    assert not changes and not ended


def test_changed_identity_or_target_is_rejected(tmp_path, backend):
    state, changes, ended = backend
    path = tmp_path / "lock.json"
    gate = account.AccountGate("mia", path)
    gate.apply(True)
    with pytest.raises(ValueError):
        account.AccountGate("parent", path)
    state["id"] = "2000"
    with pytest.raises(ValueError):
        gate.apply(False)
    assert path.exists()


def test_do_not_undo_parent_admin_change(tmp_path, backend):
    state, changes, ended = backend
    gate = account.AccountGate("mia", tmp_path / "lock.json")
    gate.apply(True)
    state["expiry"] = "12345"
    gate.apply(False)
    assert state["expiry"] == "12345"


def test_session_warning_gates_login_before_logoff(tmp_path, backend, monkeypatch):
    state, changes, ended = backend
    now, notices = [0.0], []
    monkeypatch.setattr(agent, "configure_target", lambda *a: None)
    monkeypatch.setattr(agent.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(agent, "notify", lambda title, text, **kw: notices.append(text))
    session = agent.ManagedSession({"account": "mia", "account_journal": str(tmp_path / "lock.json")})
    session.enforce(False, dry_run=False)
    assert state["expiry"] == "1" and not ended and len(notices) == 1
    now[0] = 30
    session.enforce(False, dry_run=False)
    assert ended == [("mia", "1001")]
    session.enforce(True, dry_run=False)
    assert state["expiry"] == ""


def test_missing_account_cannot_fall_back_to_locking_parent():
    with pytest.raises(ValueError, match="Kinderkonto fehlt"):
        agent.ManagedSession({})

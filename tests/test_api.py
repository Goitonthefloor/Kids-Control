"""API and policy tests for KidsControl hub."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Isolate DB before importing the app
_tmp = tempfile.mkdtemp(prefix="kidscontrol-test-")
os.environ["KIDSCONTROL_DATA_DIR"] = _tmp
os.environ["KIDSCONTROL_ADMIN_USER"] = "admin"
os.environ["KIDSCONTROL_ADMIN_PASSWORD"] = "secret"
os.environ["KIDSCONTROL_SECRET"] = "test-secret"
os.environ.pop("DATABASE_URL", None)

from app.db import AppRule, Child, Device, Schedule, SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def login(client: TestClient):
    r = client.post("/login", data={"username": "admin", "password": "secret"}, follow_redirects=False)
    assert r.status_code == 302


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_login_and_add_child_with_apps_and_device(client):
    login(client)
    r = client.post(
        "/ui/children/add",
        data={"display_name": "Mia", "slug": "mia"},
        follow_redirects=False,
    )
    assert r.status_code == 302

    r = client.post(
        "/ui/child/mia/apps/add",
        data={"label": "Minecraft", "pattern": "minecraft", "match_mode": "contains", "scope": "always"},
        follow_redirects=False,
    )
    assert r.status_code == 302

    r = client.post(
        "/ui/child/mia/devices/add",
        data={"name": "Laptop", "os_family": "linux"},
        follow_redirects=False,
    )
    assert r.status_code == 302

    db = SessionLocal()
    try:
        child = db.query(Child).filter_by(slug="mia").one()
        assert db.query(Schedule).filter_by(child_id=child.id).count() == 7
        assert db.query(AppRule).filter_by(child_id=child.id).count() == 1
        device = db.query(Device).filter_by(child_id=child.id).one()
        key = device.device_key
    finally:
        db.close()

    r = client.post(
        "/api/v1/agent/sync",
        headers={"X-Device-Key": key},
        json={"active": True, "hostname": "test-pc", "os": "linux"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "allow_session" in body
    assert body["child"]["slug"] == "mia"
    assert any(a["pattern"] == "minecraft" for a in body["blocked_apps"])


def test_agent_rejects_bad_key(client):
    r = client.post("/api/v1/agent/sync", headers={"X-Device-Key": "nope"}, json={})
    assert r.status_code == 401


def test_inventory_and_update_queue(client):
    login(client)
    client.post("/ui/children/add", data={"display_name": "Leo", "slug": "leo"}, follow_redirects=False)
    client.post(
        "/ui/child/leo/watches/add",
        data={"label": "Firefox", "package_name": "firefox"},
        follow_redirects=False,
    )
    client.post(
        "/ui/child/leo/devices/add",
        data={"name": "PC", "os_family": "linux"},
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        from app.db import Child, Device

        child = db.query(Child).filter_by(slug="leo").one()
        key = db.query(Device).filter_by(child_id=child.id).one().device_key
    finally:
        db.close()

    r = client.post(
        "/api/v1/agent/sync",
        headers={"X-Device-Key": key},
        json={
            "active": False,
            "hostname": "leo-pc",
            "os": "linux",
            "inventory": [{"name": "firefox", "version": "128.0", "source": "apt"}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "firefox" in body["watch_packages"]

    r = client.post(
        "/ui/child/leo/devices/1/update",
        data={"package_name": "firefox"},
        follow_redirects=False,
    )
    # device id may not be 1 if other tests created devices in same DB
    db = SessionLocal()
    try:
        from app.db import Child, Device, DeviceCommand, SoftwareItem

        child = db.query(Child).filter_by(slug="leo").one()
        device = db.query(Device).filter_by(child_id=child.id).one()
        item = db.query(SoftwareItem).filter_by(device_id=device.id, package_name="firefox").one()
        assert item.version == "128.0"
        device_id = device.id
    finally:
        db.close()

    r = client.post(
        f"/ui/child/leo/devices/{device_id}/update",
        data={"package_name": "firefox"},
        follow_redirects=False,
    )
    assert r.status_code == 302

    r = client.post(
        "/api/v1/agent/sync",
        headers={"X-Device-Key": key},
        json={"active": False, "os": "linux", "inventory": []},
    )
    assert r.status_code == 200
    commands = r.json()["commands"]
    assert commands and commands[0]["package_name"] == "firefox"
    cid = commands[0]["id"]

    r = client.post(
        f"/api/v1/agent/commands/{cid}/result",
        headers={"X-Device-Key": key},
        json={"status": "done", "output": "ok"},
    )
    assert r.status_code == 200
    db = SessionLocal()
    try:
        from app.db import DeviceCommand

        cmd = db.query(DeviceCommand).filter_by(id=cid).one()
        assert cmd.status == "done"
    finally:
        db.close()


def test_process_match_helper():
    from kidscontrol_agent.enforce import matches_rule

    assert matches_rule("Minecraft.Launcher", "minecraft", "contains")
    assert matches_rule("RobloxPlayerBeta.exe", "RobloxPlayerBeta.exe", "exact")
    assert matches_rule("steamwebhelper", "steam", "startswith")
    assert not matches_rule("chrome", "minecraft", "contains")

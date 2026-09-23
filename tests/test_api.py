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
os.environ["KIDSCONTROL_SETUP_PASSWORD"] = "setup-secret"
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
    db = SessionLocal()
    try:
        from app.db import DeviceCommand

        assert db.query(DeviceCommand).filter_by(id=cid).one().status == "pending"
    finally:
        db.close()

    running = client.post(
        f"/api/v1/agent/commands/{cid}/result",
        headers={"X-Device-Key": key},
        json={"status": "running", "output": ""},
    )
    assert running.status_code == 200
    quiet = client.post(
        "/api/v1/agent/sync",
        headers={"X-Device-Key": key},
        json={"active": False, "os": "linux", "inventory": []},
    )
    assert all(item["id"] != cid for item in quiet.json()["commands"])

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


def test_enroll_requires_setup_password(client):
    login(client)
    client.post("/ui/children/add", data={"display_name": "Noah", "slug": "noah"}, follow_redirects=False)
    denied = client.post("/api/v1/setup/enroll", json={"setup_password": "wrong", "child_slug": "noah", "device_name": "PC"})
    assert denied.status_code == 401
    ok = client.post(
        "/api/v1/setup/enroll",
        json={"setup_password": "setup-secret", "child_slug": "noah", "device_name": "Kinder-PC", "os": "linux"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["device_key"]
    assert body["child"]["slug"] == "noah"
    listed = client.post("/api/v1/setup/children", json={"setup_password": "setup-secret"})
    assert any(k["slug"] == "noah" for k in listed.json()["children"])


def test_setup_page_and_client_env(client, tmp_path):
    from kidscontrol_agent.setup import write_client_env

    saved = {k: os.environ.get(k) for k in ("KIDSCONTROL_ADMIN_PASSWORD", "KIDSCONTROL_SETUP_PASSWORD", "KIDSCONTROL_ADMIN_USER")}
    os.environ["KIDSCONTROL_ADMIN_PASSWORD"] = ""
    os.environ["KIDSCONTROL_SETUP_PASSWORD"] = ""
    try:
        assert client.get("/login", follow_redirects=False).headers["location"] == "/setup"
        page = client.get("/setup")
        assert page.status_code == 200
        assert "Zwei Passwörter für den Server" in page.text
        assert "nicht der Code für den Kinder-PC" in page.text
        assert "Haus-Passwort, einmal für diesen Server" in page.text
        short = client.post(
            "/setup",
            data={
                "admin_user": "admin",
                "admin_password": "short",
                "admin_password_repeat": "short",
                "setup_password": "short",
                "setup_password_repeat": "short",
                "timezone": "Europe/Berlin",
            },
        )
        assert short.status_code == 400
        done = client.post(
            "/setup",
            data={
                "admin_user": "eltern",
                "admin_password": "eltern-pass",
                "admin_password_repeat": "eltern-pass",
                "setup_password": "client-setup-pass",
                "setup_password_repeat": "client-setup-pass",
                "timezone": "Europe/Berlin",
            },
        )
        assert done.status_code == 200
        assert "Neu starten" in done.text
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    env_file = tmp_path / "client.env"
    write_client_env(env_file, server="http://127.0.0.1:8000", device_key="abc", poll_seconds=30)
    text = env_file.read_text(encoding="utf-8")
    assert "KIDSCONTROL_DEVICE_KEY=abc" in text
    assert "KIDSCONTROL_SERVER=http://127.0.0.1:8000" in text


def test_child_setup_token_language_and_app_edit(client):
    login(client)
    created = client.post("/ui/children/add", data={"display_name": "Lina"}, follow_redirects=False)
    assert created.status_code == 302
    assert "/ui/child/lina" in created.headers["location"]
    page = client.get("/ui/child/lina")
    assert "python -m kidscontrol_agent.setup" in page.text
    assert "--token" in page.text
    assert "nicht das Client-Setup-Passwort vom Server" in page.text
    client.post(
        "/ui/child/lina/apps/add",
        data={"label": "Minecraft", "pattern": "minecraft", "match_mode": "contains", "scope": "always"},
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        from app.db import AppRule, Child

        child = db.query(Child).filter_by(slug="lina").one()
        token = child.enroll_token
        rule = db.query(AppRule).filter_by(child_id=child.id).one()
        rule_id = rule.id
    finally:
        db.close()
    edited = client.post(
        f"/ui/child/lina/apps/{rule_id}",
        data={"label": "MC", "pattern": "minecraft-launcher", "match_mode": "exact", "scope": "always", "enabled": "1"},
        follow_redirects=False,
    )
    assert edited.status_code == 302
    db = SessionLocal()
    try:
        from app.db import AppRule

        rule = db.query(AppRule).filter_by(id=rule_id).one()
        assert rule.pattern == "minecraft-launcher"
        assert rule.match_mode == "exact"
        assert rule.label == "MC"
    finally:
        db.close()

    english = client.get("/lang/en", follow_redirects=False)
    assert english.status_code == 302
    dash = client.get("/dashboard")
    assert "Add a child" in dash.text

    key_body = "-----BEGIN OPENSSH PRIVATE KEY-----\nQUJD\n-----END OPENSSH PRIVATE KEY-----\n"
    enrolled = client.post(
        "/api/v1/setup/enroll",
        json={
            "token": token,
            "device_name": "Lina PC",
            "os": "linux",
            "hostname": "lina-pc",
            "ssh_user": "lina",
            "ssh_private_key": key_body,
        },
    )
    assert enrolled.status_code == 200
    assert enrolled.json()["ssh_ready"] is True
    db = SessionLocal()
    try:
        from app.db import Device

        device = db.query(Device).filter_by(name="Lina PC").one()
        assert device.ssh_enabled is True
        assert device.ssh_user == "lina"
        assert "PRIVATE KEY" in open(device.ssh_key_path, encoding="utf-8").read()
    finally:
        db.close()


def test_openssh_plan():
    from kidscontrol_agent.os_requirements import openssh_install_plan

    apt = openssh_install_plan("linux", {"apt-get"})
    assert apt[0][0] == "apt-get"
    assert "openssh-server" in apt[1]
    assert openssh_install_plan("linux", {"dnf"})[0][:2] == ["dnf", "install"]
    assert openssh_install_plan("linux", {"pacman"})[0][0] == "pacman"
    assert openssh_install_plan("windows", {"apt-get"}) == []
    assert openssh_install_plan("macos", {"apt-get"}) == []


def test_oneclick_installer_and_agent_archive(client):
    import io
    import tarfile
    import zipfile

    anon = client.get("/ui/child/noah/oneclick/linux", follow_redirects=False)
    assert anon.status_code == 302
    assert anon.headers["location"] == "/login"

    login(client)
    created = client.post("/ui/children/add", data={"display_name": "Noah"}, follow_redirects=False)
    assert created.status_code == 302
    page = client.get("/ui/child/noah")
    assert "/ui/child/noah/oneclick/linux" in page.text
    assert "/ui/child/noah/oneclick/windows" in page.text

    db = SessionLocal()
    try:
        token = db.query(Child).filter_by(slug="noah").one().enroll_token
    finally:
        db.close()

    linux = client.get("/ui/child/noah/oneclick/linux")
    assert linux.status_code == 200
    assert 'filename="kidscontrol-setup.sh"' in linux.headers["content-disposition"]
    assert token in linux.text
    assert "kidscontrol_agent.setup" in linux.text
    assert "/setup/agent.tgz" in linux.text
    assert "/opt/kidscontrol-client" in linux.text
    assert "/etc/kidscontrol/client.env" in linux.text
    assert 'exec sudo bash "$0"' in linux.text
    assert (
        "Das Kinderkonto darf kein Administrator sein. "
        "Mit sudo oder Windows-Adminrechten kann es den Dienst trotzdem stoppen."
    ) in linux.text
    assert ".local/share/kidscontrol" not in linux.text

    macos = client.get("/ui/child/noah/oneclick/macos")
    assert 'filename="kidscontrol-setup.command"' in macos.headers["content-disposition"]
    assert token in macos.text
    assert "/opt/kidscontrol-client" in macos.text
    assert "systemctl" not in macos.text
    assert ".local/share/kidscontrol" not in macos.text

    windows = client.get("/ui/child/noah/oneclick/windows")
    assert 'filename="kidscontrol-setup.cmd"' in windows.headers["content-disposition"]
    assert token in windows.text
    assert "/setup/agent.zip" in windows.text
    assert "%ProgramData%\\KidsControl" in windows.text
    assert "LOCALAPPDATA" not in windows.text
    assert "RunAs" in windows.text
    assert "\r\n" in windows.text
    assert "Das Kinderkonto darf kein Administrator sein." in windows.text

    missing = client.get("/ui/child/noah/oneclick/android")
    assert missing.status_code == 404

    tgz = client.get("/setup/agent.tgz")
    assert tgz.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(tgz.content), mode="r:gz") as archive:
        assert "kidscontrol_agent/__init__.py" in archive.getnames()

    packed = client.get("/setup/agent.zip")
    assert packed.status_code == 200
    with zipfile.ZipFile(io.BytesIO(packed.content)) as archive:
        assert "kidscontrol_agent/setup.py" in archive.namelist()


def test_platform_from_user_agent():
    from app.install_web import platform_from_user_agent, wants_install_page

    windows = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
    macos = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15"
    linux = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0"
    assert platform_from_user_agent(windows) == "windows"
    assert platform_from_user_agent(macos) == "macos"
    assert platform_from_user_agent(linux) == "linux"
    assert platform_from_user_agent("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)") is None
    assert platform_from_user_agent("curl/8.5.0") is None
    assert platform_from_user_agent("curl/8.5.0", '"Windows"') == "windows"
    assert wants_install_page("text/html,application/xhtml+xml", windows) is True
    assert wants_install_page("*/*", "curl/8.5.0") is False
    assert wants_install_page("*/*", windows) is True


def test_web_install_url_picks_system(client):
    from app.guards import clear_failures

    login(client)
    created = client.post("/ui/children/add", data={"display_name": "Nora"}, follow_redirects=False)
    assert created.status_code == 302
    page = client.get("/ui/child/nora")
    db = SessionLocal()
    try:
        token = db.query(Child).filter_by(slug="nora").one().enroll_token
    finally:
        db.close()
    assert f"/install/{token}" in page.text
    assert "Adresse für den Kinder-PC" in page.text

    windows = client.get(
        f"/install/{token}",
        headers={
            "Accept": "text/html",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        },
    )
    assert windows.status_code == 200
    assert "no-store" in windows.headers["cache-control"]
    assert f'href="/install/{token}/windows"' in windows.text
    assert "kidscontrol-setup.cmd" in windows.text
    assert 'id="kc-install"' in windows.text
    assert "Nora" in windows.text
    assert "Erkanntes System: Windows." in windows.text

    linux_page = client.get(
        f"/install/{token}?lang=en",
        headers={
            "Accept": "text/html",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
        },
    )
    assert "Detected system: Linux." in linux_page.text
    assert f'href="/install/{token}/linux"' in linux_page.text

    phone = client.get(
        f"/install/{token}",
        headers={
            "Accept": "text/html",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15",
        },
    )
    assert "nicht erkannt" in phone.text
    assert 'id="kc-install"' not in phone.text
    assert f'href="/install/{token}/macos"' in phone.text

    boot = client.get(f"/install/{token}", headers={"User-Agent": "curl/8.5.0", "Accept": "*/*"})
    assert boot.status_code == 200
    assert "uname -s" in boot.text
    assert f'TOKEN="{token}"' in boot.text
    assert '"$SERVER/install/$TOKEN/$platform"' in boot.text
    assert "platform=linux" in boot.text
    assert "platform=macos" in boot.text
    assert "kidscontrol_agent.setup" not in boot.text

    hinted = client.get(
        f"/install/{token}",
        headers={"User-Agent": "curl/8.5.0", "Accept": "*/*", "Sec-CH-UA-Platform": '"Windows"'},
    )
    assert 'filename="kidscontrol-setup.cmd"' in hinted.headers["content-disposition"]
    assert token in hinted.text

    linux = client.get(f"/install/{token}/linux")
    assert linux.status_code == 200
    assert 'filename="kidscontrol-setup.sh"' in linux.headers["content-disposition"]
    assert token in linux.text
    assert "/setup/agent.tgz" in linux.text

    missing = client.get("/install/this-token-does-not-exist")
    assert missing.status_code == 404
    assert "this-token-does-not-exist" not in missing.text
    clear_failures("install:testclient")

    gone = client.get(f"/install/{token}/android")
    assert gone.status_code == 404


def test_install_token_is_throttled(client):
    from app.guards import clear_failures

    try:
        for _ in range(8):
            blocked = client.get("/install/not-a-real-token-value", headers={"Accept": "text/html"})
            assert blocked.status_code == 404
        again = client.get("/install/not-a-real-token-value", headers={"Accept": "text/html"})
        assert again.status_code == 429
        assert "Zu viele Versuche" in again.text
    finally:
        clear_failures("install:testclient")


def test_process_match_helper():
    from kidscontrol_agent.enforce import matches_rule

    assert matches_rule("Minecraft.Launcher", "minecraft", "contains")
    assert matches_rule("RobloxPlayerBeta.exe", "RobloxPlayerBeta.exe", "exact")
    assert matches_rule("steamwebhelper", "steam", "startswith")
    assert not matches_rule("chrome", "minecraft", "contains")


NOTICE = (
    "Das Kinderkonto darf kein Administrator sein. "
    "Mit sudo oder Windows-Adminrechten kann es den Dienst trotzdem stoppen."
)


def test_usage_remainder_and_overnight_window():
    from app.policy import apply_usage_tick, in_window, minutes_until_end

    used, remainder = apply_usage_tick(0, 0, 30)
    assert (used, remainder) == (0, 30)
    used, remainder = apply_usage_tick(used, remainder, 30)
    assert (used, remainder) == (1, 0)
    assert apply_usage_tick(5, 10, 181) == (5, 10)
    assert in_window(1320, 360, 1380) is True
    assert in_window(1320, 360, 300) is True
    assert in_window(1320, 360, 600) is False
    assert in_window(900, 1110, 1000) is True
    assert minutes_until_end(1320, 360, 1380) == (24 * 60 - 1380) + 360


def test_quoted_env_unescapes_password():
    from app.config import unquote_env

    assert unquote_env('"abc\\"def"') == 'abc"def'
    assert unquote_env('"a\\\\b"') == "a\\b"


def test_install_notice_token_rotation_and_host_key(client):
    login(client)
    created = client.post("/ui/children/add", data={"display_name": "Emma"}, follow_redirects=False)
    assert created.status_code == 302
    page = client.get("/ui/child/emma")
    assert NOTICE in page.text
    assert "/ui/child/emma/enroll-token" in page.text
    db = SessionLocal()
    try:
        token = db.query(Child).filter_by(slug="emma").one().enroll_token
    finally:
        db.close()
    pubkey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKidsControlHostKeyPinTest comment"
    enrolled = client.post(
        "/api/v1/setup/enroll",
        json={
            "token": token,
            "device_name": "Emma PC",
            "os": "linux",
            "hostname": "emma-pc",
            "ssh_host_key": pubkey,
        },
    )
    assert enrolled.status_code == 200
    reused = client.post(
        "/api/v1/setup/enroll",
        json={"token": token, "device_name": "Emma PC 2", "os": "linux"},
    )
    assert reused.status_code == 401
    bad_key = client.post(
        "/api/v1/setup/enroll",
        json={"setup_password": "setup-secret", "child_slug": "emma", "device_name": "x", "ssh_host_key": "not-a-key"},
    )
    assert bad_key.status_code == 400
    db = SessionLocal()
    try:
        device = db.query(Device).filter_by(name="Emma PC").one()
        assert device.ssh_host_pubkey == "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKidsControlHostKeyPinTest"
        child = db.query(Child).filter_by(slug="emma").one()
        assert child.enroll_token != token
    finally:
        db.close()
    rotated = client.post("/ui/child/emma/enroll-token", follow_redirects=False)
    assert rotated.status_code == 302
    again = client.get("/ui/child/emma")
    assert "Neuer Einrichtungscode" in again.text


def test_package_name_and_pinned_host_key():
    import pytest

    from app.ssh_control import remote_update_script, ssh_argv
    from app.db import Device

    with pytest.raises(ValueError):
        remote_update_script("firefox;rm -rf /")
    script = remote_update_script("firefox")
    assert "firefox" in script
    assert "rm -rf" not in script

    pinned = Device(
        ssh_host="emma-pc",
        ssh_port=22,
        ssh_user="root",
        ssh_host_pubkey="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKidsControlHostKeyPinTest",
    )
    argv = ssh_argv(pinned, "true")
    assert "StrictHostKeyChecking=yes" in argv
    assert any(part.startswith("UserKnownHostsFile=") for part in argv)

    fresh = Device(ssh_host="emma-pc", ssh_port=22, ssh_user="root")
    argv = ssh_argv(fresh, "true")
    assert "StrictHostKeyChecking=accept-new" in argv


def test_lang_redirect_stays_on_site(client):
    login(client)
    remote = client.get("/lang/de", headers={"referer": "https://evil.example/phish"}, follow_redirects=False)
    assert remote.status_code == 302
    assert remote.headers["location"] == "/dashboard"
    local = client.get("/lang/en", headers={"referer": "/dashboard"}, follow_redirects=False)
    assert local.headers["location"] == "/dashboard"


def test_setup_from_lan_is_refused_until_configured():
    saved = {k: os.environ.get(k) for k in ("KIDSCONTROL_ADMIN_PASSWORD", "KIDSCONTROL_SETUP_PASSWORD")}
    os.environ["KIDSCONTROL_ADMIN_PASSWORD"] = ""
    os.environ["KIDSCONTROL_SETUP_PASSWORD"] = ""
    try:
        remote = TestClient(app, client=("10.1.2.3", 50000))
        denied = remote.get("/setup")
        assert denied.status_code == 403
        local = TestClient(app, client=("127.0.0.1", 50001))
        assert local.get("/setup").status_code == 200
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_invalid_schedule_number_does_not_crash(client):
    login(client)
    client.post("/ui/children/add", data={"display_name": "Noah"}, follow_redirects=False)
    data = {"action": "save", "wd0_start_h": "500"}
    for wd in range(7):
        data.setdefault(f"wd{wd}_start_h", "0")
        data[f"wd{wd}_start_m"] = "0"
        data[f"wd{wd}_end_h"] = "0"
        data[f"wd{wd}_end_m"] = "0"
        data[f"wd{wd}_daily"] = "0"
    data["wd0_start_h"] = "500"
    saved = client.post("/ui/child/noah/schedule", data=data, follow_redirects=False)
    assert saved.status_code == 302
    page = client.get("/ui/child/noah")
    assert "gültige Zahlen" in page.text


def test_stale_running_command_returns_to_pending(client):
    from datetime import timedelta

    from app.db import DeviceCommand, utcnow

    login(client)
    client.post("/ui/children/add", data={"display_name": "Paul", "slug": "paul"}, follow_redirects=False)
    client.post("/ui/child/paul/devices/add", data={"name": "PC", "os_family": "linux"}, follow_redirects=False)
    db = SessionLocal()
    try:
        child = db.query(Child).filter_by(slug="paul").one()
        device = db.query(Device).filter_by(child_id=child.id).one()
        cmd = DeviceCommand(
            device_id=device.id,
            kind="update_all",
            status="running",
            via="agent",
            started_at=utcnow() - timedelta(hours=2),
        )
        db.add(cmd)
        db.commit()
        key = device.device_key
        cid = cmd.id
    finally:
        db.close()
    synced = client.post(
        "/api/v1/agent/sync",
        headers={"X-Device-Key": key},
        json={"active": False, "os": "linux"},
    )
    assert synced.status_code == 200
    assert any(item["id"] == cid for item in synced.json()["commands"])
    db = SessionLocal()
    try:
        assert db.query(DeviceCommand).filter_by(id=cid).one().status == "pending"
    finally:
        db.close()

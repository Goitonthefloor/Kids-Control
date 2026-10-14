"""server.env must survive systemd's EnvironmentFile $NAME expansion."""

import os
from pathlib import Path

from app.config import load_server_env_into_process, systemd_unset_expansion
from app.passwords import hash_password, passwords_match


def test_systemd_drops_dollar_names_inside_an_argon2_hash():
    raw = "$argon2id$v=19$m=19456,t=3,p=1$ab+c$de/f"
    assert systemd_unset_expansion(raw) == "=19=19456,t=3,p=1+c/f"
    assert systemd_unset_expansion("$$keep") == "$keep"


def test_systemd_unit_does_not_load_server_env():
    text = Path("systemd/kids-control.service").read_text(encoding="utf-8")
    directives = [line.split("#", 1)[0].strip() for line in text.splitlines()]
    assert not any(line.startswith("EnvironmentFile") for line in directives)


def test_mangled_password_from_systemd_is_restored(tmp_path, monkeypatch):
    admin = hash_password("eltern-passwort")
    setup = hash_password("client-setup-pass")
    env_file = tmp_path / "server.env"
    env_file.write_text(
        f'KIDSCONTROL_ADMIN_PASSWORD="{admin}"\n'
        f'KIDSCONTROL_SETUP_PASSWORD="{setup}"\n'
        'KIDSCONTROL_SECRET="test-secret-value"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("KIDSCONTROL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KIDSCONTROL_ADMIN_PASSWORD", systemd_unset_expansion(admin))
    monkeypatch.setenv("KIDSCONTROL_SETUP_PASSWORD", systemd_unset_expansion(setup))
    assert not passwords_match("eltern-passwort", os.environ["KIDSCONTROL_ADMIN_PASSWORD"])
    load_server_env_into_process()
    assert passwords_match("eltern-passwort", os.environ["KIDSCONTROL_ADMIN_PASSWORD"])
    assert passwords_match("client-setup-pass", os.environ["KIDSCONTROL_SETUP_PASSWORD"])


def test_explicit_password_override_is_kept(tmp_path, monkeypatch):
    env_file = tmp_path / "server.env"
    env_file.write_text(
        f'KIDSCONTROL_ADMIN_PASSWORD="{hash_password("file-admin-pw")}"\n'
        f'KIDSCONTROL_SETUP_PASSWORD="{hash_password("file-setup-pw")}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("KIDSCONTROL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KIDSCONTROL_ADMIN_PASSWORD", "from-the-environment")
    monkeypatch.setenv("KIDSCONTROL_SETUP_PASSWORD", "also-from-env")
    load_server_env_into_process()
    assert os.environ["KIDSCONTROL_ADMIN_PASSWORD"] == "from-the-environment"
    assert os.environ["KIDSCONTROL_SETUP_PASSWORD"] == "also-from-env"

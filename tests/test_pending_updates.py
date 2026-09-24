"""Parsers and cache for pending Windows and Linux updates."""

from __future__ import annotations

import json

from kidscontrol_agent import inventory


APT = """
WARNING: apt does not have a stable CLI interface. Use with caution in scripts.

Listing...
firefox/noble-updates 131.0.3+build1 amd64 [upgradable from: 1:130.0.1+build1]
libssl3/noble-updates 3.0.13-0ubuntu3 amd64 [upgradable from: 3.0.13-0ubuntu1]
"""

DNF = """
Last metadata expiration check: 0:12:34 ago on Thu 24 Sep 2026.

firefox.x86_64                        129.0.2-1.fc40                        updates
Obsoleting Packages
"""

PACMAN = """
firefox 128.0.1-1 -> 129.0.2-1
vim 9.1.0-1 -> 9.1.1-1
"""

WINGET = """
Name            Id               Version  Available  Source
------------------------------------------------------------
Mozilla Firefox Mozilla.Firefox  128.0.2  130.0.1    winget

Name            ID               Version  Verfügbar  Quelle
------------------------------------------------------------
VLC media player VideoLAN.VLC    3.0.20   3.0.21     winget
Unknown package  Bad.Id          1.0      Unknown    winget
"""

BREW = """
ffmpeg (6.0) < 6.1
git (2.42.0) < 2.43.0
"""


def test_parse_apt_dnf_and_pacman():
    apt = inventory.parse_apt_upgradable(APT)
    assert apt[0] == {
        "name": "firefox",
        "version": "1:130.0.1+build1",
        "available": "131.0.3+build1",
        "source": "apt",
    }
    assert apt[1]["name"] == "libssl3"
    dnf = inventory.parse_dnf_check_update(DNF)
    assert dnf == [{"name": "firefox", "version": "", "available": "129.0.2-1.fc40", "source": "dnf"}]
    pacman = inventory.parse_pacman_qu(PACMAN)
    assert [item["name"] for item in pacman] == ["firefox", "vim"]
    assert pacman[0]["available"] == "129.0.2-1"


def test_parse_winget_english_and_german_tables():
    rows = inventory.parse_winget_upgrade(WINGET)
    assert rows == [
        {"name": "Mozilla.Firefox", "version": "128.0.2", "available": "130.0.1", "source": "winget"},
        {"name": "VideoLAN.VLC", "version": "3.0.20", "available": "3.0.21", "source": "winget"},
    ]


def test_parse_brew_verbose_and_json():
    verbose = inventory.parse_brew_outdated(BREW)
    assert verbose[0]["name"] == "ffmpeg"
    assert verbose[0]["available"] == "6.1"
    payload = {
        "formulae": [
            {"name": "git", "installed_versions": ["2.42.0"], "current_version": "2.43.0"},
        ],
        "casks": [],
    }
    parsed = inventory.parse_brew_outdated(json.dumps(payload))
    assert parsed == [{"name": "git", "version": "2.42.0", "available": "2.43.0", "source": "brew"}]


def test_refresh_keeps_cache_when_the_query_fails(tmp_path, monkeypatch):
    cache = tmp_path / "pending.json"
    monkeypatch.setattr(inventory, "PENDING_CACHE", cache)
    monkeypatch.setattr(inventory, "PENDING_TTL_SECONDS", 0)
    monkeypatch.setattr(
        inventory,
        "_collect_pending",
        lambda _os: [{"name": "firefox", "version": "1", "available": "2", "source": "apt"}],
    )
    inventory.refresh_pending_updates()
    assert inventory.cached_pending_updates()[0]["name"] == "firefox"

    monkeypatch.setattr(inventory, "_collect_pending", lambda _os: None)
    inventory.refresh_pending_updates()
    assert inventory.cached_pending_updates()[0]["name"] == "firefox"

    monkeypatch.setattr(inventory, "_collect_pending", lambda _os: [])
    inventory.refresh_pending_updates()
    assert inventory.cached_pending_updates() == []


def test_unsafe_package_names_are_dropped():
    rows = inventory.parse_apt_upgradable(
        "bad;name/stable 2 all [upgradable from: 1]\n"
        "ok/stable 2 all [upgradable from: 1]\n"
    )
    assert [item["name"] for item in rows] == ["ok"]

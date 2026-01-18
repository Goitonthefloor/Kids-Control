import os, json

PROFILE_DIR = "/opt/kids-control/app/data/profiles"

PRESETS = {
    "Schule (Standard)": {
        "week": {
            "0": {"start_min": 900, "end_min": 1110, "daily_minutes": 120},
            "1": {"start_min": 900, "end_min": 1110, "daily_minutes": 120},
            "2": {"start_min": 900, "end_min": 1110, "daily_minutes": 120},
            "3": {"start_min": 900, "end_min": 1110, "daily_minutes": 120},
            "4": {"start_min": 900, "end_min": 1200, "daily_minutes": 180},
            "5": {"start_min": 900, "end_min": 1320, "daily_minutes": 240},
            "6": {"start_min": 900, "end_min": 1200, "daily_minutes": 180},
        }
    },
    "Ferien": {
        "week": {
            "0": {"start_min": 600, "end_min": 1320, "daily_minutes": 240},
            "1": {"start_min": 600, "end_min": 1320, "daily_minutes": 240},
            "2": {"start_min": 600, "end_min": 1320, "daily_minutes": 240},
            "3": {"start_min": 600, "end_min": 1320, "daily_minutes": 240},
            "4": {"start_min": 600, "end_min": 1320, "daily_minutes": 240},
            "5": {"start_min": 600, "end_min": 1380, "daily_minutes": 300},
            "6": {"start_min": 600, "end_min": 1320, "daily_minutes": 240},
        }
    },
    "Komplett gesperrt": {
        "week": {str(i): {"start_min": 0, "end_min": 0, "daily_minutes": 0} for i in range(7)}
    },
}

def ensure_profile_dir():
    os.makedirs(PROFILE_DIR, exist_ok=True)

def _safe_name(name: str) -> str:
    out = []
    for ch in name.strip():
        if ch.isalnum() or ch in ("-", "_", " "):
            out.append(ch)
    s = "".join(out).strip().replace(" ", "_")
    return s[:60] if s else ""

def list_profiles():
    ensure_profile_dir()
    names = []
    for fn in os.listdir(PROFILE_DIR):
        if fn.endswith(".json"):
            names.append(fn[:-5].replace("_", " "))
    return sorted(names)

def save_profile(name: str, profile: dict):
    ensure_profile_dir()
    safe = _safe_name(name)
    if not safe:
        return False
    path = os.path.join(PROFILE_DIR, safe + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return True

def load_profile(name: str):
    ensure_profile_dir()
    safe = _safe_name(name)
    if not safe:
        return None
    path = os.path.join(PROFILE_DIR, safe + ".json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

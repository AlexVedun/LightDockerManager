import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "LightDockerManager"
CONFIG_FILE = CONFIG_DIR / "connections.json"


def load_profiles():
    if not CONFIG_FILE.exists():
        return []
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_profiles(profiles):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "LightDockerManager"
CONFIG_FILE = CONFIG_DIR / "settings.json"

SUPPORTED_LANGUAGES = ("en", "ru", "uk")
DEFAULT_SETTINGS = {"language": "auto"}


def load_settings():
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)
    return {**DEFAULT_SETTINGS, **data}


def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

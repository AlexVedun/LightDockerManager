import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator

from app_settings import SUPPORTED_LANGUAGES

if hasattr(sys, "_MEIPASS"):
    _BASE_DIR = Path(sys._MEIPASS)
else:
    _BASE_DIR = Path(__file__).resolve().parent

I18N_DIR = _BASE_DIR / "i18n"


def resolve_language(settings):
    language = settings.get("language", "auto")
    if language in SUPPORTED_LANGUAGES:
        return language

    system_code = QLocale.system().name().split("_")[0]
    return system_code if system_code in SUPPORTED_LANGUAGES else "en"


def install_translator(app, language):
    """English is the source language baked into the code; no .qm needed for it."""
    if language == "en":
        return None

    qm_path = I18N_DIR / f"lightdockermanager_{language}.qm"
    if not qm_path.exists():
        return None

    translator = QTranslator()
    if not translator.load(str(qm_path)):
        return None

    app.installTranslator(translator)
    return translator

import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

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
    """English is the source language baked into the code; no .qm needed for it.

    Installs up to two translators: Qt's own bundled translation for
    standard widget text this app never wraps in tr() itself (a
    QDialogButtonBox's Close/OK/Cancel, QMessageBox's Yes/No, etc.), and the
    app's own .qm for everything else. Returns whichever were actually
    installed (or None if none were) so the caller can keep them alive for
    the life of the app - translators stop applying once garbage collected.
    """
    if language == "en":
        return None

    translators = []

    qt_translator = QTranslator()
    if qt_translator.load(f"qtbase_{language}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(qt_translator)
        translators.append(qt_translator)

    qm_path = I18N_DIR / f"lightdockermanager_{language}.qm"
    if qm_path.exists():
        translator = QTranslator()
        if translator.load(str(qm_path)):
            app.installTranslator(translator)
            translators.append(translator)

    return translators or None

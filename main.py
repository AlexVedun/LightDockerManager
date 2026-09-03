import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app_settings import load_settings
from connection.manager import ConnectionManager
from i18n_loader import install_translator, resolve_language
from ui.main_window import MainWindow


def _icon_path():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "packaging" / "icon.png"


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(_icon_path())))

    settings = load_settings()
    language = resolve_language(settings)
    translator = install_translator(app, language)  # noqa: F841 (must outlive app.exec())

    connection_manager = ConnectionManager()
    try:
        connection_manager.connect_local()
    except Exception as exc:
        QMessageBox.critical(
            None,
            QCoreApplication.translate("main", "Connection Error"),
            QCoreApplication.translate("main", "Could not connect to Docker:\n{error}").format(error=exc),
        )

    window = MainWindow(connection_manager)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

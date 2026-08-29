import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from connection.manager import ConnectionManager
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    connection_manager = ConnectionManager()
    try:
        connection_manager.connect_local()
    except Exception as exc:
        QMessageBox.critical(None, "Ошибка подключения", f"Не удалось подключиться к Docker:\n{exc}")

    window = MainWindow(connection_manager)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

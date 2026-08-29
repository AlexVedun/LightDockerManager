from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget, QWidget

from ui.tables.containers_table import ContainersTab


def _placeholder_tab(text: str) -> QWidget:
    widget = QWidget()
    label = QLabel(text, widget)
    label.setStyleSheet("padding: 24px; color: gray;")
    return widget


class MainWindow(QMainWindow):
    def __init__(self, connection_manager):
        super().__init__()
        self.connection_manager = connection_manager

        self.setWindowTitle("LightDockerManager")
        self.resize(1000, 600)

        tabs = QTabWidget(self)
        tabs.addTab(ContainersTab(connection_manager), "Контейнеры")
        tabs.addTab(_placeholder_tab("Таблица образов — в разработке"), "Образы")
        tabs.addTab(_placeholder_tab("Таблица volumes — в разработке"), "Volumes")
        tabs.addTab(_placeholder_tab("Таблица сетей — в разработке"), "Сети")
        self.setCentralWidget(tabs)

        status = f"Подключено: {connection_manager.mode}" if connection_manager.is_connected() else "Нет подключения"
        self.statusBar().showMessage(status)

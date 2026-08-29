from PySide6.QtWidgets import QMainWindow, QTabWidget

from ui.tables.containers_table import ContainersTab
from ui.tables.images_table import ImagesTab
from ui.tables.networks_table import NetworksTab
from ui.tables.volumes_table import VolumesTab


class MainWindow(QMainWindow):
    def __init__(self, connection_manager):
        super().__init__()
        self.connection_manager = connection_manager

        self.setWindowTitle("LightDockerManager")
        self.resize(1000, 600)

        tabs = QTabWidget(self)
        tabs.addTab(ContainersTab(connection_manager), "Контейнеры")
        tabs.addTab(ImagesTab(connection_manager), "Образы")
        tabs.addTab(VolumesTab(connection_manager), "Volumes")
        tabs.addTab(NetworksTab(connection_manager), "Сети")
        self.setCentralWidget(tabs)

        status = f"Подключено: {connection_manager.mode}" if connection_manager.is_connected() else "Нет подключения"
        self.statusBar().showMessage(status)

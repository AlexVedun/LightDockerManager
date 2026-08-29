from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMainWindow, QTabWidget

from docker_services.events_listener import DockerEventsListener
from ui.tables.containers_table import ContainersTab
from ui.tables.images_table import ImagesTab
from ui.tables.networks_table import NetworksTab
from ui.tables.volumes_table import VolumesTab

FULL_REFRESH_INTERVAL_MS = 10000
EVENTS_RETRY_DELAY_MS = 3000


class MainWindow(QMainWindow):
    def __init__(self, connection_manager):
        super().__init__()
        self.connection_manager = connection_manager
        self.events_listener = None

        self.setWindowTitle("LightDockerManager")
        self.resize(1000, 600)

        self.containers_tab = ContainersTab(connection_manager)
        self.images_tab = ImagesTab(connection_manager)
        self.volumes_tab = VolumesTab(connection_manager)
        self.networks_tab = NetworksTab(connection_manager)
        self._tabs_by_entity = {
            "containers": self.containers_tab,
            "images": self.images_tab,
            "volumes": self.volumes_tab,
            "networks": self.networks_tab,
        }

        tabs = QTabWidget(self)
        tabs.addTab(self.containers_tab, "Контейнеры")
        tabs.addTab(self.images_tab, "Образы")
        tabs.addTab(self.volumes_tab, "Volumes")
        tabs.addTab(self.networks_tab, "Сети")
        self.setCentralWidget(tabs)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_all)
        self.refresh_timer.start(FULL_REFRESH_INTERVAL_MS)

        self._update_status()
        self._start_events_listener()

    def _start_events_listener(self):
        client = self.connection_manager.client
        if client is None:
            return
        self.events_listener = DockerEventsListener(client)
        self.events_listener.data_changed.connect(self._on_data_changed)
        self.events_listener.connection_lost.connect(self._on_events_connection_lost)
        self.events_listener.start()

    def _on_data_changed(self, entity_type):
        tab = self._tabs_by_entity.get(entity_type)
        if tab is not None:
            tab.refresh()

    def _on_events_connection_lost(self, message):
        self.statusBar().showMessage(f"Соединение с Docker events потеряно ({message}), переподключение...")
        QTimer.singleShot(EVENTS_RETRY_DELAY_MS, self._restart_events_listener)

    def _restart_events_listener(self):
        self._start_events_listener()
        self._update_status()

    def _refresh_all(self):
        for tab in self._tabs_by_entity.values():
            tab.refresh()

    def _update_status(self):
        status = f"Подключено: {self.connection_manager.mode}" if self.connection_manager.is_connected() else "Нет подключения"
        self.statusBar().showMessage(status)

    def closeEvent(self, event):
        self.refresh_timer.stop()
        if self.events_listener is not None:
            self.events_listener.stop()
            self.events_listener.wait(3000)
        super().closeEvent(event)

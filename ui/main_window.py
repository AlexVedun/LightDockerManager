from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from connection.profiles import load_profiles
from docker_services.events_listener import DockerEventsListener
from ui.dialogs.connection_dialog import ManageConnectionsDialog
from ui.tables.containers_table import ContainersTab
from ui.tables.images_table import ImagesTab
from ui.tables.networks_table import NetworksTab
from ui.tables.volumes_table import VolumesTab

FULL_REFRESH_INTERVAL_MS = 10000
EVENTS_RETRY_DELAY_MS = 3000
LOCAL_ITEM_DATA = {"type": "local"}


class MainWindow(QMainWindow):
    def __init__(self, connection_manager):
        super().__init__()
        self.connection_manager = connection_manager
        self.events_listener = None

        self.setWindowTitle("LightDockerManager")
        self.resize(1000, 600)

        self._build_menu()

        self.connection_combo = QComboBox(self)
        self.connection_combo.currentIndexChanged.connect(self._on_connection_selected)
        self._reload_connection_combo()

        self.status_label = QLabel(self)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Подключение:"))
        top_bar.addWidget(self.connection_combo)
        top_bar.addStretch()
        top_bar.addWidget(self.status_label)

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

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(top_bar)
        layout.addWidget(tabs)
        self.setCentralWidget(central)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_all)
        self.refresh_timer.start(FULL_REFRESH_INTERVAL_MS)

        self._update_status()
        self._start_events_listener()

    def _build_menu(self):
        settings_menu = self.menuBar().addMenu("Настройки")
        manage_action = settings_menu.addAction("Подключения...")
        manage_action.triggered.connect(self._open_manage_connections)

    # -- connection switching -------------------------------------------------

    def _reload_connection_combo(self):
        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        self.connection_combo.addItem("Локально", LOCAL_ITEM_DATA)

        select_index = 0
        profiles = load_profiles()
        for profile in profiles:
            self.connection_combo.addItem(profile["name"], {"type": "remote", "profile": profile})
            if self.connection_manager.mode == f"remote:{profile['name']}":
                select_index = self.connection_combo.count() - 1

        self.connection_combo.setCurrentIndex(select_index)
        self.connection_combo.blockSignals(False)

    def _on_connection_selected(self, index):
        data = self.connection_combo.itemData(index)
        if data is None:
            return
        if data["type"] == "local":
            self._switch_to_local()
        else:
            self._switch_to_remote(data["profile"])

    def _switch_to_local(self):
        try:
            self.connection_manager.connect_local()
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка подключения", str(exc))
        self._after_connection_changed()

    def _switch_to_remote(self, profile):
        try:
            self.connection_manager.connect_remote(profile)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка подключения", f"Не удалось подключиться к \"{profile['name']}\":\n{exc}")
        self._after_connection_changed()

    def _after_connection_changed(self):
        if self.events_listener is not None:
            self.events_listener.stop()
            self.events_listener.wait(3000)
            self.events_listener = None
        self._start_events_listener()
        self._refresh_all()
        self._update_status()

    def _open_manage_connections(self):
        dialog = ManageConnectionsDialog(self)
        dialog.exec()
        self._reload_connection_combo()

    # -- events / polling -------------------------------------------------

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
        if self.connection_manager.is_connected():
            self.status_label.setText(f"Подключено: {self.connection_manager.mode}")
        else:
            self.status_label.setText("Нет подключения")
        self.statusBar().clearMessage()

    def closeEvent(self, event):
        self.refresh_timer.stop()
        if self.events_listener is not None:
            self.events_listener.stop()
            self.events_listener.wait(3000)
        super().closeEvent(event)

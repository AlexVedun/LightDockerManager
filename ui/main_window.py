from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app_settings import DEFAULT_REFRESH_INTERVAL_SECONDS, load_settings, save_settings
from connection.profiles import load_profiles
from docker_services.events_listener import DockerEventsListener
from ui.dialogs.connection_dialog import ManageConnectionsDialog
from ui.tables.containers_table import ContainersTab
from ui.tables.images_table import ImagesTab
from ui.tables.networks_table import NetworksTab
from ui.tables.volumes_table import VolumesTab
from ui.volume_transfer_window import VolumeTransferWindow
from workers.task_worker import run_task

MIN_REFRESH_INTERVAL_SECONDS = 5
MAX_REFRESH_INTERVAL_SECONDS = 3600
EVENTS_RETRY_DELAY_MS = 3000
TRANSIENT_MESSAGE_MS = 6000
LOCAL_ITEM_DATA = {"type": "local"}
LANGUAGES = (("en", "English"), ("ru", "Русский"), ("uk", "Українська"))


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
        top_bar.addWidget(QLabel(self.tr("Connection:")))
        top_bar.addWidget(self.connection_combo)
        top_bar.addStretch()
        top_bar.addWidget(self.status_label)

        self.containers_tab = ContainersTab(connection_manager, notify=self._show_transient_message)
        self.images_tab = ImagesTab(connection_manager, notify=self._show_transient_message)
        self.volumes_tab = VolumesTab(connection_manager, notify=self._show_transient_message)
        self.networks_tab = NetworksTab(connection_manager, notify=self._show_transient_message)
        self._tabs_by_entity = {
            "containers": self.containers_tab,
            "images": self.images_tab,
            "volumes": self.volumes_tab,
            "networks": self.networks_tab,
        }

        tabs = QTabWidget(self)
        tabs.addTab(self.containers_tab, self.tr("Containers"))
        tabs.addTab(self.images_tab, self.tr("Images"))
        tabs.addTab(self.volumes_tab, self.tr("Volumes"))
        tabs.addTab(self.networks_tab, self.tr("Networks"))

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(top_bar)
        layout.addWidget(tabs)
        self.setCentralWidget(central)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_all)
        self.refresh_timer.start(self._refresh_interval_ms())

        self._update_status()
        self._start_events_listener()

    def _build_menu(self):
        settings_menu = self.menuBar().addMenu(self.tr("Settings"))
        manage_action = settings_menu.addAction(self.tr("Connections..."))
        manage_action.triggered.connect(self._open_manage_connections)

        language_menu = settings_menu.addMenu(self.tr("Language"))
        current_language = load_settings().get("language", "auto")
        for code, label in LANGUAGES:
            action = language_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == current_language)
            action.triggered.connect(lambda checked, c=code: self._set_language(c))

        refresh_action = settings_menu.addAction(self.tr("Refresh Interval..."))
        refresh_action.triggered.connect(self._set_refresh_interval)

        tools_menu = self.menuBar().addMenu(self.tr("Tools"))
        transfer_action = tools_menu.addAction(self.tr("Volume Transfer..."))
        transfer_action.triggered.connect(self._open_volume_transfer)

    def _set_language(self, code):
        settings = load_settings()
        settings["language"] = code
        save_settings(settings)
        QMessageBox.information(
            self,
            self.tr("Language"),
            self.tr("Restart LightDockerManager for the language change to take effect."),
        )

    def _refresh_interval_ms(self):
        settings = load_settings()
        seconds = settings.get("refresh_interval_seconds", DEFAULT_REFRESH_INTERVAL_SECONDS)
        return seconds * 1000

    def _set_refresh_interval(self):
        settings = load_settings()
        current = settings.get("refresh_interval_seconds", DEFAULT_REFRESH_INTERVAL_SECONDS)
        seconds, ok = QInputDialog.getInt(
            self,
            self.tr("Refresh Interval"),
            self.tr("Full refresh every (seconds):"),
            current,
            MIN_REFRESH_INTERVAL_SECONDS,
            MAX_REFRESH_INTERVAL_SECONDS,
        )
        if not ok:
            return
        settings["refresh_interval_seconds"] = seconds
        save_settings(settings)
        self.refresh_timer.setInterval(seconds * 1000)

    def _open_volume_transfer(self):
        window = VolumeTransferWindow(self)
        window.exec()
        self.volumes_tab.refresh()

    # -- connection switching -------------------------------------------------

    def _reload_connection_combo(self):
        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        self.connection_combo.addItem(self.tr("Local"), LOCAL_ITEM_DATA)

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
        self.connection_combo.setEnabled(False)
        self.status_label.setText(self.tr("Connecting..."))
        run_task(
            self,
            self.connection_manager.connect_local,
            on_success=lambda _: self._on_connect_finished(),
            on_error=lambda message: self._on_connect_failed(message),
        )

    def _switch_to_remote(self, profile):
        self.connection_combo.setEnabled(False)
        self.status_label.setText(self.tr("Connecting..."))
        run_task(
            self,
            self.connection_manager.connect_remote,
            profile,
            on_success=lambda _: self._on_connect_finished(),
            on_error=lambda message: self._on_connect_failed(message, profile),
        )

    def _on_connect_finished(self):
        self.connection_combo.setEnabled(True)
        self._after_connection_changed()

    def _on_connect_failed(self, message, profile=None):
        self.connection_combo.setEnabled(True)
        if profile is None:
            QMessageBox.critical(self, self.tr("Connection Error"), message)
        else:
            QMessageBox.critical(
                self,
                self.tr("Connection Error"),
                self.tr('Could not connect to "{name}":\n{error}').format(name=profile["name"], error=message),
            )
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
        self.statusBar().showMessage(
            self.tr("Docker events connection lost ({message}), reconnecting...").format(message=message)
        )
        QTimer.singleShot(EVENTS_RETRY_DELAY_MS, self._restart_events_listener)

    def _restart_events_listener(self):
        self._start_events_listener()
        self._update_status()

    def _refresh_all(self):
        for tab in self._tabs_by_entity.values():
            tab.refresh()

    def _show_transient_message(self, message):
        self.statusBar().showMessage(message, TRANSIENT_MESSAGE_MS)

    def _update_status(self):
        if self.connection_manager.is_connected():
            self.status_label.setText(self.tr("Connected: {mode}").format(mode=self.connection_manager.mode))
        else:
            self.status_label.setText(self.tr("Not connected"))
        self.statusBar().clearMessage()

    def closeEvent(self, event):
        self.refresh_timer.stop()
        if self.events_listener is not None:
            self.events_listener.stop()
            self.events_listener.wait(3000)
        for owner in (self, *self._tabs_by_entity.values()):
            for worker in list(getattr(owner, "_background_workers", [])):
                worker.wait(3000)
        super().closeEvent(event)

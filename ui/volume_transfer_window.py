import docker
import docker.errors
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from connection.profiles import load_profiles
from docker_services.volume_transfer import transfer_volume
from ui.dialogs.confirm_dialog import confirm

LOCAL_LABEL = "Локально"


class TransferWorker(QThread):
    log_message = Signal(str)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, source_client, source_volume, dest_client, dest_volume):
        super().__init__()
        self.source_client = source_client
        self.source_volume = source_volume
        self.dest_client = dest_client
        self.dest_volume = dest_volume

    def run(self):
        try:
            transfer_volume(
                self.source_client,
                self.source_volume,
                self.dest_client,
                self.dest_volume,
                log=self.log_message.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit()


class HostPicker(QGroupBox):
    """Lets the user pick 'Local' or a saved SSH profile and shows its volumes."""

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.combo = QComboBox(self)
        self.combo.addItem(LOCAL_LABEL, {"type": "local"})
        for profile in load_profiles():
            self.combo.addItem(profile["name"], {"type": "remote", "profile": profile})
        self.combo.currentIndexChanged.connect(self._reload_volumes)

        self.volume_combo = QComboBox(self)

        layout = QVBoxLayout(self)
        layout.addWidget(self.combo)
        layout.addWidget(self.volume_combo)

        self._client_cache = {}
        self._reload_volumes()

    def _get_client(self):
        data = self.combo.currentData()
        if data is None:
            return None
        key = data["type"] if data["type"] == "local" else data["profile"]["name"]
        if key in self._client_cache:
            return self._client_cache[key]
        try:
            if data["type"] == "local":
                client = docker.from_env()
            else:
                profile = data["profile"]
                base_url = f"ssh://{profile['user']}@{profile['host']}:{profile.get('port', 22)}"
                client = docker.DockerClient(base_url=base_url, use_ssh_client=True)
            client.ping()
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка подключения", str(exc))
            return None
        self._client_cache[key] = client
        return client

    def _reload_volumes(self):
        self.volume_combo.clear()
        client = self._get_client()
        if client is None:
            return
        try:
            for volume in client.volumes.list():
                self.volume_combo.addItem(volume.name)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))

    def selected_client(self):
        return self._get_client()

    def selected_volume(self):
        return self.volume_combo.currentText()

    def selected_host_label(self):
        return self.combo.currentText()


class VolumeTransferWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Перенос Volume")
        self.resize(600, 500)
        self.worker = None

        self.source_picker = HostPicker("Источник")
        self.dest_picker = HostPicker("Назначение")

        pickers_row = QHBoxLayout()
        pickers_row.addWidget(self.source_picker)
        pickers_row.addWidget(self.dest_picker)

        self.dest_name_edit = QLineEdit(self)
        self.dest_name_edit.setPlaceholderText("Имя volume на назначении (по умолчанию — как у источника)")

        self.btn_transfer = QPushButton("Перенести")
        self.btn_transfer.clicked.connect(self._start_transfer)

        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addLayout(pickers_row)
        layout.addWidget(QLabel("Имя volume на назначении:"))
        layout.addWidget(self.dest_name_edit)
        layout.addWidget(self.btn_transfer)
        layout.addWidget(self.log_view)

    def _start_transfer(self):
        source_client = self.source_picker.selected_client()
        dest_client = self.dest_picker.selected_client()
        source_volume = self.source_picker.selected_volume()
        dest_volume = self.dest_name_edit.text().strip() or source_volume

        if source_client is None or dest_client is None:
            return
        if not source_volume:
            QMessageBox.warning(self, "Перенос volume", "Выберите volume-источник.")
            return
        if source_client is dest_client and source_volume == dest_volume:
            QMessageBox.warning(self, "Перенос volume", "Источник и назначение совпадают.")
            return

        if not confirm(
            self,
            "Перенос volume",
            f"Перенести volume \"{source_volume}\" ({self.source_picker.selected_host_label()}) "
            f"в volume \"{dest_volume}\" ({self.dest_picker.selected_host_label()})?\n\n"
            "Если volume с таким именем уже существует на назначении, его содержимое будет дополнено/перезаписано.",
        ):
            return

        self.btn_transfer.setEnabled(False)
        self.log_view.clear()

        self.worker = TransferWorker(source_client, source_volume, dest_client, dest_volume)
        self.worker.log_message.connect(self.log_view.appendPlainText)
        self.worker.finished_ok.connect(self._on_finished_ok)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_finished_ok(self):
        self.btn_transfer.setEnabled(True)
        QMessageBox.information(self, "Перенос volume", "Перенос завершён успешно.")

    def _on_failed(self, message):
        self.btn_transfer.setEnabled(True)
        self.log_view.appendPlainText(f"[Ошибка] {message}")
        QMessageBox.critical(self, "Ошибка переноса", message)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(5000)
        super().closeEvent(event)

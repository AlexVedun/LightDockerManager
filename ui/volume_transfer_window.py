from pathlib import Path

import docker
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from connection.manager import CLIENT_TIMEOUT_SECONDS
from connection.profiles import load_profiles
from docker_services.formatting import human_size
from docker_services.volume_transfer import export_volume, import_volume, transfer_volume
from ui.dialogs.confirm_dialog import confirm
from ui.icons import standard_icon
from workers.task_worker import run_task


def _volume_name_from_archive(file_path):
    name = Path(file_path).name
    return name[:-4] if name.lower().endswith(".tar") else name


class VolumeOperationWorker(QThread):
    log_message = Signal(str)
    # Qt's `int` signal type is signed 32-bit and wraps after 2 GiB. Use
    # Python objects so byte counters retain Python's arbitrary precision.
    progress = Signal(object, object)  # transferred, total (int or None if unmeasured)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, operation, *args, **kwargs):
        super().__init__()
        self.operation = operation
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.operation(
                *self.args,
                log=self.log_message.emit,
                progress=self.progress.emit,
                **self.kwargs,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit()


class TransferWorker(VolumeOperationWorker):
    def __init__(self, source_client, source_volume, dest_client, dest_volume):
        super().__init__(transfer_volume, source_client, source_volume, dest_client, dest_volume)


class HostPicker(QGroupBox):
    """Lets the user pick 'Local' or a saved SSH profile and shows its volumes."""

    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.combo = QComboBox(self)
        self.combo.addItem(self.tr("Local"), {"type": "local"})
        for profile in load_profiles():
            self.combo.addItem(profile["name"], {"type": "remote", "profile": profile})
        self.combo.currentIndexChanged.connect(self._reload_volumes)

        self.volume_combo = QComboBox(self)

        layout = QVBoxLayout(self)
        layout.addWidget(self.combo)
        layout.addWidget(self.volume_combo)

        self._client_cache = {}
        self._pending_selection = None
        self._reload_volumes()

    def preselect_volume(self, name):
        index = self.volume_combo.findText(name)
        if index >= 0:
            self.volume_combo.setCurrentIndex(index)
        else:
            self._pending_selection = name

    @staticmethod
    def _cache_key(data):
        return data["type"] if data["type"] == "local" else data["profile"]["name"]

    @staticmethod
    def _connect_and_list_volume_names(data):
        if data["type"] == "local":
            client = docker.from_env(timeout=CLIENT_TIMEOUT_SECONDS)
        else:
            profile = data["profile"]
            base_url = f"ssh://{profile['user']}@{profile['host']}:{profile.get('port', 22)}"
            client = docker.DockerClient(base_url=base_url, use_ssh_client=True, timeout=CLIENT_TIMEOUT_SECONDS)
        client.ping()
        names = [volume.name for volume in client.volumes.list()]
        return client, names

    def _reload_volumes(self):
        self.volume_combo.clear()
        data = self.combo.currentData()
        if data is None:
            return
        key = self._cache_key(data)
        cached = self._client_cache.get(key)
        if cached is not None:
            for name in cached["volumes"]:
                self.volume_combo.addItem(name)
            return
        self.combo.setEnabled(False)
        run_task(
            self,
            self._connect_and_list_volume_names,
            data,
            on_success=lambda result: self._on_volumes_loaded(key, result),
            on_error=lambda message: self._on_volumes_failed(key, message),
        )

    def _on_volumes_loaded(self, key, result):
        client, names = result
        self._client_cache[key] = {"client": client, "volumes": names}
        self.combo.setEnabled(True)
        current_data = self.combo.currentData()
        if current_data is None or self._cache_key(current_data) != key:
            return
        self.volume_combo.clear()
        for name in names:
            self.volume_combo.addItem(name)
        if self._pending_selection is not None:
            index = self.volume_combo.findText(self._pending_selection)
            if index >= 0:
                self.volume_combo.setCurrentIndex(index)
            self._pending_selection = None

    def _on_volumes_failed(self, key, message):
        self.combo.setEnabled(True)
        current_data = self.combo.currentData()
        if current_data is not None and self._cache_key(current_data) == key:
            QMessageBox.critical(self, self.tr("Connection Error"), message)

    def selected_client(self):
        data = self.combo.currentData()
        if data is None:
            return None
        cached = self._client_cache.get(self._cache_key(data))
        return cached["client"] if cached else None

    def selected_volume(self):
        return self.volume_combo.currentText()

    def selected_host_label(self):
        return self.combo.currentText()

    def volume_names(self):
        data = self.combo.currentData()
        if data is None:
            return set()
        cached = self._client_cache.get(self._cache_key(data))
        return set(cached["volumes"]) if cached else set()

    def remember_volume(self, name):
        data = self.combo.currentData()
        if data is None:
            return
        cached = self._client_cache.get(self._cache_key(data))
        if cached is None or name in cached["volumes"]:
            return
        cached["volumes"].append(name)
        self.volume_combo.addItem(name)


class VolumeTransferWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Volume Transfer"))
        self.resize(600, 500)
        self.worker = None

        self.source_picker = HostPicker(self.tr("Source"))
        self.dest_picker = HostPicker(self.tr("Destination"))

        pickers_row = QHBoxLayout()
        pickers_row.addWidget(self.source_picker)
        pickers_row.addWidget(self.dest_picker)

        self.dest_name_edit = QLineEdit(self)
        self.dest_name_edit.setPlaceholderText(self.tr("Volume name on destination (defaults to source name)"))

        self.btn_transfer = QPushButton(standard_icon("SP_ArrowRight"), self.tr("Transfer"))
        self.btn_transfer.clicked.connect(self._start_transfer)
        self.btn_export = QPushButton(standard_icon("SP_DialogSaveButton"), self.tr("Export..."))
        self.btn_export.clicked.connect(self._start_export)
        self.btn_import = QPushButton(standard_icon("SP_DialogOpenButton"), self.tr("Import..."))
        self.btn_import.clicked.connect(self._start_import)

        actions_row = QHBoxLayout()
        actions_row.addWidget(self.btn_transfer)
        actions_row.addWidget(self.btn_export)
        actions_row.addWidget(self.btn_import)

        # The transfer measures the volume's on-disk size upfront (via `du`
        # inside the helper container) to drive a real percentage; if that
        # measurement fails for some reason, falls back to a busy animation
        # instead of a fabricated number.
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()

        self.progress_label = QLabel(self)
        self.progress_label.hide()

        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addLayout(pickers_row)
        layout.addWidget(QLabel(self.tr("Volume name on destination:")))
        layout.addWidget(self.dest_name_edit)
        layout.addLayout(actions_row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.log_view)

    def _start_transfer(self):
        source_client = self.source_picker.selected_client()
        dest_client = self.dest_picker.selected_client()
        source_volume = self.source_picker.selected_volume()
        dest_volume = self.dest_name_edit.text().strip() or source_volume

        if source_client is None or dest_client is None:
            QMessageBox.warning(
                self,
                self.tr("Volume Transfer"),
                self.tr("Still connecting to the selected host(s), please try again shortly."),
            )
            return
        if not source_volume:
            QMessageBox.warning(self, self.tr("Volume Transfer"), self.tr("Please select a source volume."))
            return
        if source_client is dest_client and source_volume == dest_volume:
            QMessageBox.warning(self, self.tr("Volume Transfer"), self.tr("Source and destination are the same."))
            return

        if not confirm(
            self,
            self.tr("Volume Transfer"),
            self.tr(
                'Transfer volume "{source_volume}" ({source_host}) '
                'to volume "{dest_volume}" ({dest_host})?\n\n'
                "If a volume with this name already exists on the destination, its contents may be overwritten."
            ).format(
                source_volume=source_volume,
                source_host=self.source_picker.selected_host_label(),
                dest_volume=dest_volume,
                dest_host=self.dest_picker.selected_host_label(),
            ),
        ):
            return

        self._run_operation(
            TransferWorker(source_client, source_volume, dest_client, dest_volume),
            self.tr("Transfer completed successfully."),
            self.tr("Transfer Error"),
        )

    def _start_export(self):
        client = self.source_picker.selected_client()
        volume_name = self.source_picker.selected_volume()
        if client is None:
            QMessageBox.warning(
                self,
                self.tr("Volume Export"),
                self.tr("Still connecting to the selected host, please try again shortly."),
            )
            return
        if not volume_name:
            QMessageBox.warning(self, self.tr("Volume Export"), self.tr("Please select a source volume."))
            return

        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            self.tr("Export Volume"),
            f"{volume_name}.tar",
            self.tr("Tar archives (*.tar);;All files (*)"),
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".tar"):
            file_path += ".tar"

        self._run_operation(
            VolumeOperationWorker(export_volume, client, volume_name, file_path),
            self.tr("Export completed successfully."),
            self.tr("Export Error"),
        )

    def _start_import(self):
        client = self.dest_picker.selected_client()
        if client is None:
            QMessageBox.warning(
                self,
                self.tr("Volume Import"),
                self.tr("Still connecting to the selected host, please try again shortly."),
            )
            return

        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Import Volume"),
            "",
            self.tr("Tar archives (*.tar);;All files (*)"),
        )
        if not file_path:
            return

        volume_name = _volume_name_from_archive(file_path)
        if not volume_name:
            QMessageBox.warning(
                self,
                self.tr("Volume Import"),
                self.tr("Could not determine a volume name from the selected file."),
            )
            return

        resolved = self._resolve_import_destination(volume_name)
        if resolved is None:
            return
        volume_name, overwrite = resolved
        self._run_operation(
            VolumeOperationWorker(import_volume, client, volume_name, file_path, overwrite=overwrite),
            self.tr("Import completed successfully."),
            self.tr("Import Error"),
            on_success=lambda: self.dest_picker.remember_volume(volume_name),
        )

    def _resolve_import_destination(self, volume_name):
        while volume_name in self.dest_picker.volume_names():
            answer = QMessageBox.question(
                self,
                self.tr("Volume Import"),
                self.tr('Volume "{name}" already exists.\n\nOverwrite?').format(name=volume_name),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                return volume_name, True

            while True:
                volume_name, accepted = QInputDialog.getText(
                    self,
                    self.tr("Volume Import"),
                    self.tr("New volume name:"),
                    text=volume_name,
                )
                if not accepted:
                    return None
                volume_name = volume_name.strip()
                if volume_name:
                    break
                QMessageBox.warning(
                    self,
                    self.tr("Volume Import"),
                    self.tr("Volume name cannot be empty."),
                )
        return volume_name, False

    def _run_operation(self, worker, success_message, error_title, on_success=None):
        for button in (self.btn_transfer, self.btn_export, self.btn_import):
            button.setEnabled(False)
        self.log_view.clear()
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText(self.tr("Transferred: 0 B"))
        self.progress_bar.show()
        self.progress_label.show()

        self._success_message = success_message
        self._error_title = error_title
        self._operation_success_callback = on_success
        self.worker = worker
        self.worker.log_message.connect(self.log_view.appendPlainText)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_finished_ok)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, transferred, total):
        if total:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(min(100, int(transferred * 100 / total)))
            self.progress_label.setText(
                self.tr("Transferred: {done} / ~{total}").format(done=human_size(transferred), total=human_size(total))
            )
        else:
            self.progress_label.setText(self.tr("Transferred: {size}").format(size=human_size(transferred)))

    def _on_finished_ok(self):
        for button in (self.btn_transfer, self.btn_export, self.btn_import):
            button.setEnabled(True)
        self.progress_bar.hide()
        if self._operation_success_callback is not None:
            self._operation_success_callback()
        QMessageBox.information(self, self.tr("Volume Transfer"), self._success_message)

    def _on_failed(self, message):
        for button in (self.btn_transfer, self.btn_export, self.btn_import):
            button.setEnabled(True)
        self.progress_bar.hide()
        self.log_view.appendPlainText(self.tr("[Error] {message}").format(message=message))
        QMessageBox.critical(self, self._error_title, message)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            # There is no way to safely cancel an operation mid-flight (the
            # blocking archive read/write can't be interrupted from here),
            # and destroying this window while its QThread is still running
            # would tear the thread down mid-run - so the window simply
            # can't be closed until the operation finishes or fails on its
            # own.
            QMessageBox.information(
                self,
                self.tr("Volume Transfer"),
                self.tr("A volume operation is still running. Please wait for it to finish or fail before closing."),
            )
            event.ignore()
            return
        super().closeEvent(event)

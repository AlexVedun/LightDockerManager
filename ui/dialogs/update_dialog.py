from PySide6.QtCore import QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from docker_services.formatting import human_size
from updater import can_self_update, download_and_install_update
from version import __version__


class UpdateDownloadWorker(QThread):
    progress = Signal(object, object)  # transferred, total
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, release_info, parent=None):
        super().__init__(parent)
        self.release_info = release_info

    def run(self):
        try:
            download_and_install_update(self.release_info, progress=self.progress.emit)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit()


class UpdateDialog(QDialog):
    def __init__(self, release_info, parent=None):
        super().__init__(parent)
        self.release_info = release_info
        self.worker = None

        self.setWindowTitle(self.tr("Update Available"))
        self.resize(520, 380)

        latest_version = release_info["version"]
        header_label = QLabel(
            self.tr("A new version of LightDockerManager is available: <b>{latest}</b> (current: {current}).").format(
                latest=latest_version,
                current=__version__,
            ),
            self,
        )
        header_label.setWordWrap(True)

        notes_label = QLabel(self.tr("Release notes:"), self)
        self.notes_view = QPlainTextEdit(self)
        self.notes_view.setReadOnly(True)
        self.notes_view.setPlainText(release_info.get("body") or self.tr("No release notes provided."))

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()

        self.progress_label = QLabel(self)
        self.progress_label.hide()

        self.btn_update = QPushButton(self.tr("Update and Restart"), self)
        self.btn_open_page = QPushButton(self.tr("Open Release Page"), self)
        self.btn_later = QPushButton(self.tr("Later"), self)

        self._self_update_supported = bool(release_info.get("asset")) and can_self_update()
        if not self._self_update_supported:
            self.btn_update.hide()

        self.btn_update.clicked.connect(self._start_update)
        self.btn_open_page.clicked.connect(self._open_release_page)
        self.btn_later.clicked.connect(self.reject)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()
        buttons_row.addWidget(self.btn_update)
        buttons_row.addWidget(self.btn_open_page)
        buttons_row.addWidget(self.btn_later)

        layout = QVBoxLayout(self)
        layout.addWidget(header_label)
        layout.addWidget(notes_label)
        layout.addWidget(self.notes_view)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        layout.addLayout(buttons_row)

    def _open_release_page(self):
        QDesktopServices.openUrl(QUrl(self.release_info["html_url"]))
        self.accept()

    def _start_update(self):
        self.btn_update.setEnabled(False)
        self.btn_open_page.setEnabled(False)
        self.btn_later.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText(self.tr("Downloading update..."))
        self.progress_bar.show()
        self.progress_label.show()

        self.worker = UpdateDownloadWorker(self.release_info, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_finished_ok)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, transferred, total):
        if not total:
            asset = self.release_info.get("asset") or {}
            total = asset.get("size") or None
        if total:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(min(100, int(transferred * 100 / total)))
            self.progress_label.setText(
                self.tr("Downloaded: {done} / {total}").format(
                    done=human_size(transferred),
                    total=human_size(total),
                )
            )
        else:
            self.progress_label.setText(self.tr("Downloaded: {done}").format(done=human_size(transferred)))

    def _on_finished_ok(self):
        self.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _on_failed(self, message):
        self.btn_update.setEnabled(True)
        self.btn_open_page.setEnabled(True)
        self.btn_later.setEnabled(True)
        self.progress_bar.hide()
        self.progress_label.hide()
        QMessageBox.critical(
            self,
            self.tr("Update Error"),
            self.tr("Failed to install update:\n{error}").format(error=message),
        )

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

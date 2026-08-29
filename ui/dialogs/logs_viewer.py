import docker.errors
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout

POLL_INTERVAL_MS = 1000
INITIAL_TAIL_LINES = 200


class LogsViewerDialog(QDialog):
    def __init__(self, container, container_name, parent=None):
        super().__init__(parent)
        self.container = container
        self._last_timestamp = None

        self.setWindowTitle(f"Логи: {container_name}")
        self.resize(800, 500)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(5000)

        layout = QVBoxLayout(self)
        layout.addWidget(self.text_edit)

        self._load_initial_logs()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_new_logs)
        self.timer.start(POLL_INTERVAL_MS)

    def _load_initial_logs(self):
        try:
            raw = self.container.logs(tail=INITIAL_TAIL_LINES, timestamps=True)
        except docker.errors.APIError as exc:
            self.text_edit.setPlainText(f"[Ошибка получения логов: {exc}]")
            return
        text = raw.decode("utf-8", errors="replace")
        self.text_edit.setPlainText(text)
        self._remember_last_timestamp(text)
        self._scroll_to_bottom()

    def _poll_new_logs(self):
        try:
            kwargs = {"timestamps": True}
            if self._last_timestamp:
                kwargs["since"] = self._last_timestamp
            raw = self.container.logs(**kwargs)
        except docker.errors.APIError:
            return
        text = raw.decode("utf-8", errors="replace")
        if not text:
            return
        self.text_edit.appendPlainText(text.rstrip("\n"))
        self._remember_last_timestamp(text)
        self._scroll_to_bottom()

    def _remember_last_timestamp(self, text):
        lines = [line for line in text.splitlines() if line]
        if lines:
            self._last_timestamp = lines[-1].split(" ", 1)[0]

    def _scroll_to_bottom(self):
        scrollbar = self.text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

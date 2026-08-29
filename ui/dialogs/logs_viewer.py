from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout

from workers.task_worker import run_task

POLL_INTERVAL_MS = 1000
INITIAL_TAIL_LINES = 200


def _fetch_logs(container, since):
    kwargs = {"timestamps": True}
    if since:
        kwargs["since"] = since
    else:
        kwargs["tail"] = INITIAL_TAIL_LINES
    raw = container.logs(**kwargs)
    return raw.decode("utf-8", errors="replace")


class LogsViewerDialog(QDialog):
    def __init__(self, container, container_name, parent=None):
        super().__init__(parent)
        self.container = container
        self._last_timestamp = None
        self._fetching = False

        self.setWindowTitle(self.tr("Logs: {name}").format(name=container_name))
        self.resize(800, 500)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(5000)

        layout = QVBoxLayout(self)
        layout.addWidget(self.text_edit)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_logs)
        self.timer.start(POLL_INTERVAL_MS)
        self._poll_logs()

    def _poll_logs(self):
        if self._fetching:
            return
        self._fetching = True
        is_initial = self._last_timestamp is None
        run_task(
            self,
            _fetch_logs,
            self.container,
            self._last_timestamp,
            on_success=lambda text: self._on_logs_fetched(text, is_initial),
            on_error=lambda message: self._on_logs_failed(message, is_initial),
        )

    def _on_logs_fetched(self, text, is_initial):
        self._fetching = False
        if is_initial:
            self.text_edit.setPlainText(text)
            self._remember_last_timestamp(text)
            self._scroll_to_bottom()
        elif text:
            self.text_edit.appendPlainText(text.rstrip("\n"))
            self._remember_last_timestamp(text)
            self._scroll_to_bottom()

    def _on_logs_failed(self, message, is_initial):
        self._fetching = False
        if is_initial:
            self.text_edit.setPlainText(self.tr("[Error fetching logs: {error}]").format(error=message))

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

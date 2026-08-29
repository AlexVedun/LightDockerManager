import docker.errors
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from docker_services import images as images_service
from docker_services.formatting import human_size, short_timestamp, summarize_prune_result
from ui.dialogs.confirm_dialog import confirm
from ui.dialogs.inspect_dialog import InspectDialog
from ui.tables.base import DictRowsTableModel

COLUMNS = ["Repository:Tag", "Image ID", "Размер", "Используется", "Создан"]
ACCESSORS = [
    lambda r: r["tags"],
    lambda r: r["id"],
    lambda r: human_size(r["size"]),
    lambda r: "да" if r["used"] else "нет",
    lambda r: short_timestamp(r["created"]),
]
USED_COLUMN = 3
USED_COLOR = QColor("#2ecc71")
UNUSED_COLOR = QColor("#95a5a6")


def _used_color(row):
    return USED_COLOR if row["used"] else UNUSED_COLOR


class ImagesTab(QWidget):
    def __init__(self, connection_manager, parent=None):
        super().__init__(parent)
        self.connection_manager = connection_manager
        self.model = DictRowsTableModel(COLUMNS, ACCESSORS, color_column=USED_COLUMN, color_getter=_used_color)

        self.view = QTableView(self)
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.verticalHeader().setVisible(False)

        self.btn_refresh = QPushButton("Обновить")
        self.btn_pull = QPushButton("Pull")
        self.btn_remove = QPushButton("Remove")
        self.btn_inspect = QPushButton("Inspect")
        self.btn_prune = QPushButton("Prune")

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_pull.clicked.connect(self._pull_image)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_inspect.clicked.connect(self._show_inspect)
        self.btn_prune.clicked.connect(self._prune)

        toolbar = QHBoxLayout()
        for btn in (self.btn_refresh, self.btn_pull, self.btn_remove, self.btn_inspect, self.btn_prune):
            toolbar.addWidget(btn)
        toolbar.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self.view)

        self.refresh()

    def refresh(self):
        client = self.connection_manager.client
        if client is None:
            self.model.set_rows([])
            return
        try:
            rows = images_service.list_images(client)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
            return
        self.model.set_rows(rows)

    def _selected_row(self):
        indexes = self.view.selectionModel().selectedRows()
        if not indexes:
            return None
        return self.model.row_at(indexes[0].row())

    def _pull_image(self):
        client = self.connection_manager.client
        if client is None:
            return
        repo_tag, ok = QInputDialog.getText(self, "Pull образа", "Имя образа (например nginx:latest):")
        if not ok or not repo_tag.strip():
            return
        try:
            images_service.pull(client, repo_tag.strip())
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
        self.refresh()

    def _remove_selected(self):
        row = self._selected_row()
        if row is None:
            return
        if not confirm(self, "Удалить образ", f"Удалить образ \"{row['tags']}\"?"):
            return
        try:
            images_service.remove(row["image"], force=True)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
        self.refresh()

    def _show_inspect(self):
        row = self._selected_row()
        if row is None:
            return
        image = row["image"]
        try:
            image.reload()
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
            return
        InspectDialog(f"Inspect: {row['tags']}", image.attrs, self).exec()

    def _prune(self):
        client = self.connection_manager.client
        if client is None:
            return
        if not confirm(self, "Prune образов", "Удалить все неиспользуемые образы?"):
            return
        try:
            result = images_service.prune(client)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
            return
        QMessageBox.information(self, "Prune завершён", summarize_prune_result(result))
        self.refresh()

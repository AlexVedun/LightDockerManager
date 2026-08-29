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

USED_COLUMN = 3
USED_COLOR = QColor("#2ecc71")
UNUSED_COLOR = QColor("#95a5a6")


def _used_color(row):
    return USED_COLOR if row["used"] else UNUSED_COLOR


class ImagesTab(QWidget):
    def __init__(self, connection_manager, parent=None):
        super().__init__(parent)
        self.connection_manager = connection_manager

        columns = [
            self.tr("Repository:Tag"),
            self.tr("Image ID"),
            self.tr("Size"),
            self.tr("Used"),
            self.tr("Created"),
        ]
        accessors = [
            lambda r: r["tags"],
            lambda r: r["id"],
            lambda r: human_size(r["size"]),
            lambda r: self.tr("Yes") if r["used"] else self.tr("No"),
            lambda r: short_timestamp(r["created"]),
        ]
        self.model = DictRowsTableModel(columns, accessors, color_column=USED_COLUMN, color_getter=_used_color)

        self.view = QTableView(self)
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.verticalHeader().setVisible(False)

        self.btn_refresh = QPushButton(self.tr("Refresh"))
        self.btn_pull = QPushButton(self.tr("Pull"))
        self.btn_remove = QPushButton(self.tr("Remove"))
        self.btn_inspect = QPushButton(self.tr("Inspect"))
        self.btn_prune = QPushButton(self.tr("Prune"))

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
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
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
        repo_tag, ok = QInputDialog.getText(self, self.tr("Pull Image"), self.tr("Image name (e.g. nginx:latest):"))
        if not ok or not repo_tag.strip():
            return
        try:
            images_service.pull(client, repo_tag.strip())
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
        self.refresh()

    def _remove_selected(self):
        row = self._selected_row()
        if row is None:
            return
        if not confirm(self, self.tr("Remove Image"), self.tr('Remove image "{tags}"?').format(tags=row["tags"])):
            return
        try:
            images_service.remove(row["image"], force=True)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
        self.refresh()

    def _show_inspect(self):
        row = self._selected_row()
        if row is None:
            return
        image = row["image"]
        try:
            image.reload()
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
            return
        InspectDialog(self.tr("Inspect: {tags}").format(tags=row["tags"]), image.attrs, self).exec()

    def _prune(self):
        client = self.connection_manager.client
        if client is None:
            return
        if not confirm(self, self.tr("Prune Images"), self.tr("Remove all unused images?")):
            return
        try:
            result = images_service.prune(client)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
            return
        QMessageBox.information(self, self.tr("Prune Complete"), summarize_prune_result(result))
        self.refresh()

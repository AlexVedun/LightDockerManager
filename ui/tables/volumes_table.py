import docker.errors
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from docker_services import volumes as volumes_service
from docker_services.formatting import human_size, summarize_prune_result
from ui.dialogs.confirm_dialog import confirm
from ui.dialogs.inspect_dialog import InspectDialog
from ui.tables.base import DictRowsTableModel
from ui.volume_transfer_window import VolumeTransferWindow

USED_COLUMN = 3
USED_COLOR = QColor("#2ecc71")
UNUSED_COLOR = QColor("#95a5a6")


def _used_color(row):
    return USED_COLOR if row["used"] else UNUSED_COLOR


class VolumesTab(QWidget):
    def __init__(self, connection_manager, parent=None):
        super().__init__(parent)
        self.connection_manager = connection_manager

        columns = [
            self.tr("Name"),
            self.tr("Driver"),
            self.tr("Mountpoint"),
            self.tr("Used"),
            self.tr("Size"),
        ]
        accessors = [
            lambda r: r["name"],
            lambda r: r["driver"],
            lambda r: r["mountpoint"],
            lambda r: self.tr("Yes") if r["used"] else self.tr("No"),
            lambda r: human_size(r["size"]),
        ]
        self.model = DictRowsTableModel(columns, accessors, color_column=USED_COLUMN, color_getter=_used_color)

        self.view = QTableView(self)
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.verticalHeader().setVisible(False)

        self.btn_refresh = QPushButton(self.tr("Refresh"))
        self.btn_remove = QPushButton(self.tr("Remove"))
        self.btn_inspect = QPushButton(self.tr("Inspect"))
        self.btn_prune = QPushButton(self.tr("Prune"))
        self.btn_transfer = QPushButton(self.tr("Transfer to another host"))

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_inspect.clicked.connect(self._show_inspect)
        self.btn_prune.clicked.connect(self._prune)
        self.btn_transfer.clicked.connect(self._open_transfer_window)

        toolbar = QHBoxLayout()
        for btn in (self.btn_refresh, self.btn_remove, self.btn_inspect, self.btn_prune, self.btn_transfer):
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
            rows = volumes_service.list_volumes(client)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
            return
        self.model.set_rows(rows)

    def _selected_row(self):
        indexes = self.view.selectionModel().selectedRows()
        if not indexes:
            return None
        return self.model.row_at(indexes[0].row())

    def _remove_selected(self):
        row = self._selected_row()
        if row is None:
            return
        if not confirm(self, self.tr("Remove Volume"), self.tr('Remove volume "{name}"?').format(name=row["name"])):
            return
        try:
            volumes_service.remove(row["volume"], force=True)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
        self.refresh()

    def _show_inspect(self):
        row = self._selected_row()
        if row is None:
            return
        volume = row["volume"]
        try:
            volume.reload()
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
            return
        InspectDialog(self.tr("Inspect: {name}").format(name=row["name"]), volume.attrs, self).exec()

    def _prune(self):
        client = self.connection_manager.client
        if client is None:
            return
        if not confirm(self, self.tr("Prune Volumes"), self.tr("Remove all unused volumes?")):
            return
        try:
            result = volumes_service.prune(client)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
            return
        QMessageBox.information(self, self.tr("Prune Complete"), summarize_prune_result(result))
        self.refresh()

    def _open_transfer_window(self):
        row = self._selected_row()
        window = VolumeTransferWindow(self)
        if row is not None:
            window.source_picker.volume_combo.setCurrentText(row["name"])
        window.exec()
        self.refresh()

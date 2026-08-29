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
from docker_services.common import reload_and_get_attrs
from docker_services.formatting import human_size, summarize_prune_result
from ui.dialogs.confirm_dialog import confirm
from ui.dialogs.inspect_dialog import InspectDialog
from ui.tables.base import DictRowsTableModel
from ui.volume_transfer_window import VolumeTransferWindow
from workers.task_worker import run_task

USED_COLUMN = 3
USED_COLOR = QColor("#2ecc71")
UNUSED_COLOR = QColor("#95a5a6")


def _used_color(row):
    return USED_COLOR if row["used"] else UNUSED_COLOR


class VolumesTab(QWidget):
    def __init__(self, connection_manager, parent=None):
        super().__init__(parent)
        self.connection_manager = connection_manager
        self._refreshing = False

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
        if self._refreshing:
            return
        self._refreshing = True
        run_task(
            self,
            volumes_service.list_volumes,
            client,
            on_success=self._on_refresh_succeeded,
            on_error=self._on_refresh_failed,
        )

    def _on_refresh_succeeded(self, rows):
        self._refreshing = False
        self.model.set_rows(rows)

    def _on_refresh_failed(self, message):
        self._refreshing = False
        QMessageBox.critical(self, self.tr("Docker Error"), message)

    def _selected_row(self):
        indexes = self.view.selectionModel().selectedRows()
        if not indexes:
            return None
        return self.model.row_at(indexes[0].row())

    def _on_action_failed(self, message):
        QMessageBox.critical(self, self.tr("Docker Error"), message)
        self.refresh()

    def _remove_selected(self):
        row = self._selected_row()
        if row is None:
            return
        if not confirm(self, self.tr("Remove Volume"), self.tr('Remove volume "{name}"?').format(name=row["name"])):
            return
        run_task(
            self,
            volumes_service.remove,
            row["volume"],
            force=True,
            on_success=lambda _: self.refresh(),
            on_error=self._on_action_failed,
        )

    def _show_inspect(self):
        row = self._selected_row()
        if row is None:
            return
        name = row["name"]
        run_task(
            self,
            reload_and_get_attrs,
            row["volume"],
            on_success=lambda attrs: InspectDialog(self.tr("Inspect: {name}").format(name=name), attrs, self).exec(),
            on_error=self._on_action_failed,
        )

    def _prune(self):
        client = self.connection_manager.client
        if client is None:
            return
        if not confirm(self, self.tr("Prune Volumes"), self.tr("Remove all unused volumes?")):
            return
        run_task(
            self,
            volumes_service.prune,
            client,
            on_success=self._on_prune_succeeded,
            on_error=self._on_action_failed,
        )

    def _on_prune_succeeded(self, result):
        QMessageBox.information(self, self.tr("Prune Complete"), summarize_prune_result(result))
        self.refresh()

    def _open_transfer_window(self):
        row = self._selected_row()
        window = VolumeTransferWindow(self)
        if row is not None:
            window.source_picker.preselect_volume(row["name"])
        window.exec()
        self.refresh()

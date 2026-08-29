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

from docker_services import networks as networks_service
from docker_services.formatting import summarize_prune_result
from ui.dialogs.confirm_dialog import confirm
from ui.dialogs.inspect_dialog import InspectDialog
from ui.tables.base import DictRowsTableModel

USED_COLUMN = 4
USED_COLOR = QColor("#2ecc71")
UNUSED_COLOR = QColor("#95a5a6")


def _used_color(row):
    return USED_COLOR if row["used"] else UNUSED_COLOR


class NetworksTab(QWidget):
    def __init__(self, connection_manager, parent=None):
        super().__init__(parent)
        self.connection_manager = connection_manager

        columns = [
            self.tr("Name"),
            self.tr("Driver"),
            self.tr("Scope"),
            self.tr("Connected Containers"),
            self.tr("Used"),
        ]
        accessors = [
            lambda r: r["name"],
            lambda r: r["driver"],
            lambda r: r["scope"],
            lambda r: r["containers"],
            lambda r: self.tr("Yes") if r["used"] else self.tr("No"),
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
        self.btn_connect = QPushButton(self.tr("Connect Container"))
        self.btn_disconnect = QPushButton(self.tr("Disconnect Container"))
        self.btn_prune = QPushButton(self.tr("Prune"))

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_inspect.clicked.connect(self._show_inspect)
        self.btn_connect.clicked.connect(self._connect_container)
        self.btn_disconnect.clicked.connect(self._disconnect_container)
        self.btn_prune.clicked.connect(self._prune)

        toolbar = QHBoxLayout()
        for btn in (
            self.btn_refresh,
            self.btn_remove,
            self.btn_inspect,
            self.btn_connect,
            self.btn_disconnect,
            self.btn_prune,
        ):
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
            rows = networks_service.list_networks(client)
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
        if not confirm(self, self.tr("Remove Network"), self.tr('Remove network "{name}"?').format(name=row["name"])):
            return
        try:
            networks_service.remove(row["network"])
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
        self.refresh()

    def _show_inspect(self):
        row = self._selected_row()
        if row is None:
            return
        network = row["network"]
        try:
            network.reload()
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
            return
        InspectDialog(self.tr("Inspect: {name}").format(name=row["name"]), network.attrs, self).exec()

    def _pick_container(self, title):
        client = self.connection_manager.client
        if client is None:
            return None
        containers = client.containers.list(all=True)
        if not containers:
            QMessageBox.information(self, title, self.tr("No containers available."))
            return None
        names = [c.name for c in containers]
        name, ok = QInputDialog.getItem(self, title, self.tr("Container:"), names, editable=False)
        if not ok:
            return None
        return next(c for c in containers if c.name == name)

    def _connect_container(self):
        row = self._selected_row()
        if row is None:
            return
        container = self._pick_container(self.tr("Connect Container to Network"))
        if container is None:
            return
        try:
            networks_service.connect(row["network"], container)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
        self.refresh()

    def _disconnect_container(self):
        row = self._selected_row()
        if row is None:
            return
        container = self._pick_container(self.tr("Disconnect Container from Network"))
        if container is None:
            return
        try:
            networks_service.disconnect(row["network"], container)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
        self.refresh()

    def _prune(self):
        client = self.connection_manager.client
        if client is None:
            return
        if not confirm(self, self.tr("Prune Networks"), self.tr("Remove all unused networks?")):
            return
        try:
            result = networks_service.prune(client)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, self.tr("Docker Error"), str(exc))
            return
        QMessageBox.information(self, self.tr("Prune Complete"), summarize_prune_result(result))
        self.refresh()

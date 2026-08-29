import functools

from PySide6.QtCore import QSortFilterProxyModel, Qt
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
from docker_services.common import reload_and_get_attrs
from docker_services.formatting import summarize_prune_result
from ui.dialogs.confirm_dialog import confirm
from ui.dialogs.inspect_dialog import InspectDialog
from ui.tables.base import DictRowsTableModel, install_column_sorting, install_row_checkboxes
from workers.task_worker import run_bulk_task, run_task

NAME_COLUMN = 0
USED_COLUMN = 4
USED_COLOR = QColor("#2ecc71")
UNUSED_COLOR = QColor("#95a5a6")


def _used_color(row):
    return USED_COLOR if row["used"] else UNUSED_COLOR


class NetworksTab(QWidget):
    def __init__(self, connection_manager, parent=None):
        super().__init__(parent)
        self.connection_manager = connection_manager
        self._refreshing = False

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
        sort_accessors = {
            USED_COLUMN: lambda r: r["used"],
        }
        self.model = DictRowsTableModel(
            columns,
            accessors,
            row_key=lambda r: r["network"].id,
            color_column=USED_COLUMN,
            color_getter=_used_color,
            sort_accessors=sort_accessors,
        )
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole)

        self.view = QTableView(self)
        self.view.setModel(self.proxy)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().resizeSection(self.model.CHECKBOX_COLUMN, 28)
        self.view.verticalHeader().setVisible(False)
        install_row_checkboxes(self.view, self.proxy, self.model.CHECKBOX_COLUMN)
        install_column_sorting(
            self.view,
            self.proxy,
            sortable_columns={NAME_COLUMN + 1},
            checkbox_column=self.model.CHECKBOX_COLUMN,
            on_toggle_all=lambda: self.model.set_all_checked(not self.model.has_checked()),
        )

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
        if self._refreshing:
            return
        self._refreshing = True
        run_task(
            self,
            networks_service.list_networks,
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
        source_index = self.proxy.mapToSource(indexes[0])
        return self.model.row_at(source_index.row())

    def _target_rows(self):
        checked = self.model.checked_rows()
        if checked:
            return checked
        row = self._selected_row()
        return [row] if row is not None else []

    def _on_action_failed(self, message):
        QMessageBox.critical(self, self.tr("Docker Error"), message)
        self.refresh()

    def _on_bulk_action_finished(self, errors):
        if errors:
            QMessageBox.critical(self, self.tr("Docker Error"), "\n".join(errors))
        self.refresh()

    def _remove_selected(self):
        rows = self._target_rows()
        if not rows:
            return
        names = ", ".join(row["name"] for row in rows)
        if not confirm(self, self.tr("Remove Network"), self.tr('Remove network(s) "{names}"?').format(names=names)):
            return
        tasks = [functools.partial(networks_service.remove, row["network"]) for row in rows]
        run_bulk_task(self, tasks, self._on_bulk_action_finished)

    def _show_inspect(self):
        row = self._selected_row()
        if row is None:
            return
        name = row["name"]
        run_task(
            self,
            reload_and_get_attrs,
            row["network"],
            on_success=lambda attrs: InspectDialog(self.tr("Inspect: {name}").format(name=name), attrs, self).exec(),
            on_error=self._on_action_failed,
        )

    def _pick_container_from_list(self, title, containers):
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
        client = self.connection_manager.client
        if client is None:
            return
        run_task(
            self,
            lambda: client.containers.list(all=True),
            on_success=lambda containers: self._prompt_and_connect(row, containers),
            on_error=self._on_action_failed,
        )

    def _prompt_and_connect(self, row, containers):
        container = self._pick_container_from_list(self.tr("Connect Container to Network"), containers)
        if container is None:
            return
        run_task(
            self,
            networks_service.connect,
            row["network"],
            container,
            on_success=lambda _: self.refresh(),
            on_error=self._on_action_failed,
        )

    def _disconnect_container(self):
        row = self._selected_row()
        if row is None:
            return
        client = self.connection_manager.client
        if client is None:
            return
        run_task(
            self,
            lambda: client.containers.list(all=True),
            on_success=lambda containers: self._prompt_and_disconnect(row, containers),
            on_error=self._on_action_failed,
        )

    def _prompt_and_disconnect(self, row, containers):
        container = self._pick_container_from_list(self.tr("Disconnect Container from Network"), containers)
        if container is None:
            return
        run_task(
            self,
            networks_service.disconnect,
            row["network"],
            container,
            on_success=lambda _: self.refresh(),
            on_error=self._on_action_failed,
        )

    def _prune(self):
        client = self.connection_manager.client
        if client is None:
            return
        if not confirm(self, self.tr("Prune Networks"), self.tr("Remove all unused networks?")):
            return
        run_task(
            self,
            networks_service.prune,
            client,
            on_success=self._on_prune_succeeded,
            on_error=self._on_action_failed,
        )

    def _on_prune_succeeded(self, result):
        QMessageBox.information(self, self.tr("Prune Complete"), summarize_prune_result(result))
        self.refresh()

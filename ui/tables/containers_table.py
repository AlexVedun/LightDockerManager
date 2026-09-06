import functools

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

from docker_services import containers as containers_service
from docker_services.common import reload_and_get_attrs
from ui.dialogs.confirm_dialog import confirm
from ui.dialogs.inspect_dialog import InspectDialog
from ui.dialogs.logs_viewer import LogsViewerDialog
from ui.tables.base import (
    DictRowsTableModel,
    GroupedSortProxyModel,
    install_column_sorting,
    install_column_width_persistence,
    install_row_checkboxes,
)
from workers.task_worker import run_bulk_task, run_task

BULLET_COLUMN = 0
NAME_COLUMN = 1
STATUS_COLUMN = 3
STATUS_COLORS = {
    "running": QColor("#2ecc71"),
    "paused": QColor("#f1c40f"),
}
DEFAULT_STATUS_COLOR = QColor("#95a5a6")


class ContainersTab(QWidget):
    def __init__(self, connection_manager, parent=None, notify=None):
        super().__init__(parent)
        self.connection_manager = connection_manager
        self._refreshing = False
        self._notify = notify or (lambda message: None)

        columns = [self.tr(""), self.tr("Name"), self.tr("Image"), self.tr("Status"), self.tr("Ports")]
        accessors = [
            lambda r: "●",
            lambda r: r["name"],
            lambda r: r["image"],
            lambda r: r["status"],
            lambda r: r["ports"],
        ]
        self.model = DictRowsTableModel(
            columns,
            accessors,
            row_key=lambda r: r["container"].id,
            color_column=BULLET_COLUMN,
            color_getter=lambda r: STATUS_COLORS.get(r["status"], DEFAULT_STATUS_COLOR),
            group_key=lambda r: r["project"],
            group_label=lambda key: key if key else self.tr("Standalone"),
        )
        self.proxy = GroupedSortProxyModel(self)
        self.proxy.setSourceModel(self.model)

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
            sortable_columns={NAME_COLUMN + 1, STATUS_COLUMN + 1},
            checkbox_column=self.model.CHECKBOX_COLUMN,
            on_toggle_all=lambda: self.model.set_all_checked(not self.model.has_checked()),
            table_key="containers",
        )
        install_column_width_persistence(self.view, "containers", checkbox_column=self.model.CHECKBOX_COLUMN)
        self.proxy.layoutChanged.connect(self._apply_group_spans)

        self.btn_refresh = QPushButton(self.tr("Refresh"))
        self.btn_start = QPushButton(self.tr("Start"))
        self.btn_stop = QPushButton(self.tr("Stop"))
        self.btn_restart = QPushButton(self.tr("Restart"))
        self.btn_pause = QPushButton(self.tr("Pause"))
        self.btn_unpause = QPushButton(self.tr("Unpause"))
        self.btn_remove = QPushButton(self.tr("Remove"))
        self.btn_logs = QPushButton(self.tr("Logs"))
        self.btn_inspect = QPushButton(self.tr("Inspect"))

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_start.clicked.connect(lambda: self._run_bulk_action(containers_service.start))
        self.btn_stop.clicked.connect(lambda: self._run_bulk_action(containers_service.stop))
        self.btn_restart.clicked.connect(lambda: self._run_bulk_action(containers_service.restart))
        self.btn_pause.clicked.connect(lambda: self._run_bulk_action(containers_service.pause))
        self.btn_unpause.clicked.connect(lambda: self._run_bulk_action(containers_service.unpause))
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_logs.clicked.connect(self._show_logs)
        self.btn_inspect.clicked.connect(self._show_inspect)

        toolbar = QHBoxLayout()
        for btn in (
            self.btn_refresh,
            self.btn_start,
            self.btn_stop,
            self.btn_restart,
            self.btn_pause,
            self.btn_unpause,
            self.btn_remove,
            self.btn_logs,
            self.btn_inspect,
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
            self._apply_group_spans()
            return
        if self._refreshing:
            return
        self._refreshing = True
        run_task(
            self,
            containers_service.list_containers,
            client,
            on_success=self._on_refresh_succeeded,
            on_error=self._on_refresh_failed,
        )

    def _on_refresh_succeeded(self, rows):
        self._refreshing = False
        self.model.set_rows(rows)
        self._apply_group_spans()

    def _apply_group_spans(self):
        self.view.clearSpans()
        column_count = self.model.columnCount()
        for proxy_row in range(self.proxy.rowCount()):
            source_row = self.proxy.mapToSource(self.proxy.index(proxy_row, 0)).row()
            if self.model.is_group_row(source_row):
                self.view.setSpan(proxy_row, 0, 1, column_count)

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

    def _on_bulk_action_finished(self, errors, stale):
        self.model.set_all_checked(False)
        if stale:
            self._notify(self.tr("%n item(s) no longer exist and were skipped.", None, len(stale)))
        if errors:
            QMessageBox.critical(self, self.tr("Docker Error"), "\n".join(errors))
        self.refresh()

    def _on_action_failed(self, message):
        QMessageBox.critical(self, self.tr("Docker Error"), message)
        self.refresh()

    def _on_item_gone(self, message):
        self._notify(message)
        self.refresh()

    def _run_bulk_action(self, action):
        rows = self._target_rows()
        if not rows:
            return
        tasks = [functools.partial(action, row["container"]) for row in rows]
        run_bulk_task(self, tasks, self._on_bulk_action_finished)

    def _remove_selected(self):
        rows = self._target_rows()
        if not rows:
            return
        names = ", ".join(row["name"] for row in rows)
        if not confirm(self, self.tr("Remove Container"), self.tr('Remove container(s) "{names}"?').format(names=names)):
            return
        tasks = [functools.partial(containers_service.remove, row["container"], force=True) for row in rows]
        run_bulk_task(self, tasks, self._on_bulk_action_finished)

    def _show_logs(self):
        row = self._selected_row()
        if row is None:
            return
        dialog = LogsViewerDialog(row["container"], row["name"], self)
        dialog.exec()

    def _show_inspect(self):
        row = self._selected_row()
        if row is None:
            return
        name = row["name"]
        run_task(
            self,
            reload_and_get_attrs,
            row["container"],
            on_success=lambda attrs: InspectDialog(self.tr("Inspect: {name}").format(name=name), attrs, self).exec(),
            on_error=self._on_action_failed,
            on_not_found=self._on_item_gone,
        )

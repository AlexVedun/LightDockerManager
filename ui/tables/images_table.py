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

from docker_services import images as images_service
from docker_services.common import reload_and_get_attrs
from docker_services.formatting import human_size, short_timestamp, summarize_prune_result
from ui.dialogs.confirm_dialog import confirm
from ui.dialogs.inspect_dialog import InspectDialog
from ui.icons import standard_icon, trash_icon
from ui.tables.base import (
    DictRowsTableModel,
    install_column_sorting,
    install_column_width_persistence,
    install_foreground_color_delegate,
    install_row_checkboxes,
    install_selection_persistence,
)
from workers.task_worker import run_bulk_task, run_task

TAGS_COLUMN = 0
SIZE_COLUMN = 2
USED_COLUMN = 3
CREATED_COLUMN = 4
USED_COLOR = QColor("#2ecc71")
UNUSED_COLOR = QColor("#95a5a6")


def _used_color(row):
    return USED_COLOR if row["used"] else UNUSED_COLOR


class ImagesTab(QWidget):
    def __init__(self, connection_manager, parent=None, notify=None):
        super().__init__(parent)
        self.connection_manager = connection_manager
        self._refreshing = False
        self._notify = notify or (lambda message: None)

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
        sort_accessors = {
            SIZE_COLUMN: lambda r: r["size"] if r["size"] is not None else -1,
            USED_COLUMN: lambda r: r["used"],
            CREATED_COLUMN: lambda r: r["created"] or "",
        }
        row_key = lambda r: r["image"].id
        self.model = DictRowsTableModel(
            columns,
            accessors,
            row_key=row_key,
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
        install_foreground_color_delegate(self.view)
        install_column_sorting(
            self.view,
            self.proxy,
            sortable_columns={TAGS_COLUMN + 1, SIZE_COLUMN + 1, USED_COLUMN + 1, CREATED_COLUMN + 1},
            checkbox_column=self.model.CHECKBOX_COLUMN,
            on_toggle_all=lambda: self.model.set_all_checked(not self.model.has_checked()),
            table_key="images",
        )
        install_column_width_persistence(self.view, "images", checkbox_column=self.model.CHECKBOX_COLUMN)
        install_selection_persistence(self.view, self.proxy, self.model, row_key)

        self.btn_refresh = QPushButton(standard_icon("SP_BrowserReload"), self.tr("Refresh"))
        self.btn_pull = QPushButton(standard_icon("SP_ArrowDown"), self.tr("Pull"))
        self.btn_remove = QPushButton(trash_icon(), self.tr("Remove"))
        self.btn_inspect = QPushButton(standard_icon("SP_MessageBoxInformation"), self.tr("Inspect"))
        self.btn_prune = QPushButton(standard_icon("SP_DialogResetButton"), self.tr("Prune"))

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
        if self._refreshing:
            return
        self._refreshing = True
        run_task(
            self,
            images_service.list_images,
            client,
            on_success=self._on_refresh_succeeded,
            on_error=self._on_refresh_failed,
        )

    def _on_refresh_succeeded(self, rows):
        self._refreshing = False
        self.model.set_rows(rows)

    def _on_refresh_failed(self, message):
        self._refreshing = False
        self._notify(message)

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

    def _on_item_gone(self, message):
        self._notify(message)
        self.refresh()

    def _on_bulk_action_finished(self, errors, stale):
        self.model.set_all_checked(False)
        if stale:
            self._notify(self.tr("%n item(s) no longer exist and were skipped.", None, len(stale)))
        if errors:
            QMessageBox.critical(self, self.tr("Docker Error"), "\n".join(errors))
        self.refresh()

    def _pull_image(self):
        client = self.connection_manager.client
        if client is None:
            return
        repo_tag, ok = QInputDialog.getText(self, self.tr("Pull Image"), self.tr("Image name (e.g. nginx:latest):"))
        if not ok or not repo_tag.strip():
            return
        run_task(
            self,
            images_service.pull,
            client,
            repo_tag.strip(),
            on_success=lambda _: self.refresh(),
            on_error=self._on_action_failed,
        )

    def _remove_selected(self):
        rows = self._target_rows()
        if not rows:
            return
        tags = ", ".join(row["tags"] for row in rows)
        if not confirm(self, self.tr("Remove Image"), self.tr('Remove image(s) "{tags}"?').format(tags=tags)):
            return
        tasks = [functools.partial(images_service.remove, row["image"], force=True) for row in rows]
        run_bulk_task(self, tasks, self._on_bulk_action_finished)

    def _show_inspect(self):
        row = self._selected_row()
        if row is None:
            return
        tags = row["tags"]
        run_task(
            self,
            reload_and_get_attrs,
            row["image"],
            on_success=lambda attrs: InspectDialog(self.tr("Inspect: {tags}").format(tags=tags), attrs, self).exec(),
            on_error=self._on_action_failed,
            on_not_found=self._on_item_gone,
        )

    def _prune(self):
        client = self.connection_manager.client
        if client is None:
            return
        if not confirm(self, self.tr("Prune Images"), self.tr("Remove all unused images?")):
            return
        run_task(
            self,
            images_service.prune,
            client,
            on_success=self._on_prune_succeeded,
            on_error=self._on_action_failed,
        )

    def _on_prune_succeeded(self, result):
        QMessageBox.information(self, self.tr("Prune Complete"), summarize_prune_result(result))
        self.refresh()

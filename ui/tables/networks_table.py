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

COLUMNS = ["Имя", "Driver", "Scope", "Подключённые контейнеры", "Используется"]
ACCESSORS = [
    lambda r: r["name"],
    lambda r: r["driver"],
    lambda r: r["scope"],
    lambda r: r["containers"],
    lambda r: "да" if r["used"] else "нет",
]
USED_COLUMN = 4
USED_COLOR = QColor("#2ecc71")
UNUSED_COLOR = QColor("#95a5a6")


def _used_color(row):
    return USED_COLOR if row["used"] else UNUSED_COLOR


class NetworksTab(QWidget):
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
        self.btn_remove = QPushButton("Remove")
        self.btn_inspect = QPushButton("Inspect")
        self.btn_connect = QPushButton("Подключить контейнер")
        self.btn_disconnect = QPushButton("Отключить контейнер")
        self.btn_prune = QPushButton("Prune")

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
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
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
        if not confirm(self, "Удалить сеть", f"Удалить сеть \"{row['name']}\"?"):
            return
        try:
            networks_service.remove(row["network"])
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
        self.refresh()

    def _show_inspect(self):
        row = self._selected_row()
        if row is None:
            return
        network = row["network"]
        try:
            network.reload()
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
            return
        InspectDialog(f"Inspect: {row['name']}", network.attrs, self).exec()

    def _pick_container(self, title):
        client = self.connection_manager.client
        if client is None:
            return None
        containers = client.containers.list(all=True)
        if not containers:
            QMessageBox.information(self, title, "Нет доступных контейнеров.")
            return None
        names = [c.name for c in containers]
        name, ok = QInputDialog.getItem(self, title, "Контейнер:", names, editable=False)
        if not ok:
            return None
        return next(c for c in containers if c.name == name)

    def _connect_container(self):
        row = self._selected_row()
        if row is None:
            return
        container = self._pick_container("Подключить контейнер к сети")
        if container is None:
            return
        try:
            networks_service.connect(row["network"], container)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
        self.refresh()

    def _disconnect_container(self):
        row = self._selected_row()
        if row is None:
            return
        container = self._pick_container("Отключить контейнер от сети")
        if container is None:
            return
        try:
            networks_service.disconnect(row["network"], container)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
        self.refresh()

    def _prune(self):
        client = self.connection_manager.client
        if client is None:
            return
        if not confirm(self, "Prune сетей", "Удалить все неиспользуемые сети?"):
            return
        try:
            result = networks_service.prune(client)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
            return
        QMessageBox.information(self, "Prune завершён", summarize_prune_result(result))
        self.refresh()

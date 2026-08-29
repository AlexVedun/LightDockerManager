import docker.errors
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
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
from ui.dialogs.confirm_dialog import confirm

COLUMNS = ["", "Name", "Image", "Status", "Ports"]

STATUS_COLORS = {
    "running": QColor("#2ecc71"),
    "paused": QColor("#f1c40f"),
}
DEFAULT_STATUS_COLOR = QColor("#95a5a6")


class ContainersTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_at(self, row_index):
        return self._rows[row_index]

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            return {
                0: "●",
                1: row["name"],
                2: row["image"],
                3: row["status"],
                4: row["ports"],
            }.get(col)

        if role == Qt.ForegroundRole and col == 0:
            return STATUS_COLORS.get(row["status"], DEFAULT_STATUS_COLOR)

        return None


class ContainersTab(QWidget):
    def __init__(self, connection_manager, parent=None):
        super().__init__(parent)
        self.connection_manager = connection_manager
        self.model = ContainersTableModel()

        self.view = QTableView(self)
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.verticalHeader().setVisible(False)

        self.btn_refresh = QPushButton("Обновить")
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_restart = QPushButton("Restart")
        self.btn_pause = QPushButton("Pause")
        self.btn_unpause = QPushButton("Unpause")
        self.btn_remove = QPushButton("Remove")

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_start.clicked.connect(lambda: self._run_action(containers_service.start))
        self.btn_stop.clicked.connect(lambda: self._run_action(containers_service.stop))
        self.btn_restart.clicked.connect(lambda: self._run_action(containers_service.restart))
        self.btn_pause.clicked.connect(lambda: self._run_action(containers_service.pause))
        self.btn_unpause.clicked.connect(lambda: self._run_action(containers_service.unpause))
        self.btn_remove.clicked.connect(self._remove_selected)

        toolbar = QHBoxLayout()
        for btn in (
            self.btn_refresh,
            self.btn_start,
            self.btn_stop,
            self.btn_restart,
            self.btn_pause,
            self.btn_unpause,
            self.btn_remove,
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
            rows = containers_service.list_containers(client)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
            return
        self.model.set_rows(rows)

    def _selected_row(self):
        indexes = self.view.selectionModel().selectedRows()
        if not indexes:
            return None
        return self.model.row_at(indexes[0].row())

    def _run_action(self, action):
        row = self._selected_row()
        if row is None:
            return
        try:
            action(row["container"])
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
        self.refresh()

    def _remove_selected(self):
        row = self._selected_row()
        if row is None:
            return
        if not confirm(self, "Удалить контейнер", f"Удалить контейнер \"{row['name']}\"?"):
            return
        try:
            containers_service.remove(row["container"], force=True)
        except docker.errors.APIError as exc:
            QMessageBox.critical(self, "Ошибка Docker", str(exc))
        self.refresh()

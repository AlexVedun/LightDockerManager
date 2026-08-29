from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class DictRowsTableModel(QAbstractTableModel):
    """Generic read-only table model over a list of dict rows."""

    def __init__(self, columns, accessors, color_column=None, color_getter=None):
        super().__init__()
        self._columns = columns
        self._accessors = accessors
        self._color_column = color_column
        self._color_getter = color_getter
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
        return len(self._columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._columns[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            return self._accessors[col](row)

        if role == Qt.ForegroundRole and col == self._color_column and self._color_getter:
            return self._color_getter(row)

        return None

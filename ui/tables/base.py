from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app_settings import load_settings, save_settings


class DictRowsTableModel(QAbstractTableModel):
    """Generic table model over a list of dict rows.

    Column 0 is always a checkbox column (keyed by `row_key`) so several rows
    can be selected at once for a bulk action; the caller's `columns` /
    `accessors` describe the remaining, display-only columns.
    """

    CHECKBOX_COLUMN = 0

    def __init__(self, columns, accessors, row_key, color_column=None, color_getter=None, sort_accessors=None):
        super().__init__()
        self._columns = [""] + list(columns)
        self._accessors = accessors
        self._row_key = row_key
        self._color_column = None if color_column is None else color_column + 1
        self._color_getter = color_getter
        self._sort_accessors = sort_accessors or {}
        self._checked = set()
        self._rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        live_keys = {self._row_key(row) for row in rows}
        self._checked &= live_keys
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

        if col == self.CHECKBOX_COLUMN:
            if role == Qt.CheckStateRole:
                return Qt.Checked if self._row_key(row) in self._checked else Qt.Unchecked
            return None

        field_col = col - 1

        if role == Qt.DisplayRole:
            return self._accessors[field_col](row)

        if role == Qt.UserRole:
            return self._sort_accessors.get(field_col, self._accessors[field_col])(row)

        if role == Qt.ForegroundRole and col == self._color_column and self._color_getter:
            return self._color_getter(row)

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == self.CHECKBOX_COLUMN:
            key = self._row_key(self._rows[index.row()])
            if value == Qt.Checked:
                self._checked.add(key)
            else:
                self._checked.discard(key)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True
        return False

    def checked_rows(self):
        return [row for row in self._rows if self._row_key(row) in self._checked]

    def has_checked(self):
        return bool(self._checked)

    def set_all_checked(self, checked):
        if not self._rows:
            return
        self._checked = {self._row_key(row) for row in self._rows} if checked else set()
        top_left = self.index(0, self.CHECKBOX_COLUMN)
        bottom_right = self.index(len(self._rows) - 1, self.CHECKBOX_COLUMN)
        self.dataChanged.emit(top_left, bottom_right, [Qt.CheckStateRole])


def install_row_checkboxes(view, proxy, checkbox_column):
    """Toggles a row's checkbox on any click within the checkbox column.

    Handled explicitly (rather than relying on Qt.ItemIsUserCheckable and the
    platform style's native, often tiny, checkbox-indicator hit rect) so a
    click anywhere in the cell toggles it.
    """

    def _on_clicked(index):
        if index.column() != checkbox_column:
            return
        current = index.data(Qt.CheckStateRole)
        new_state = Qt.Unchecked if current == Qt.Checked else Qt.Checked
        proxy.setData(index, new_state, Qt.CheckStateRole)

    view.clicked.connect(_on_clicked)


def install_column_sorting(view, proxy, sortable_columns, checkbox_column=None, on_toggle_all=None, table_key=None):
    """Wires header clicks to sort `proxy`, restricted to `sortable_columns`.

    Clicking the checkbox column's header (if given) toggles select-all/none
    instead of sorting. Shows a sort-direction indicator arrow in the header,
    and when `table_key` is given, remembers the applied sort column/order
    across restarts.
    """
    header = view.horizontalHeader()
    header.setSectionsClickable(True)
    header.setSortIndicatorShown(True)
    state = {"column": None, "order": Qt.AscendingOrder}

    if table_key is not None:
        saved = load_settings().get("table_sort", {}).get(table_key)
        if saved is not None and saved.get("column") in sortable_columns:
            state["column"] = saved["column"]
            state["order"] = Qt.DescendingOrder if saved.get("order") == "desc" else Qt.AscendingOrder
            header.setSortIndicator(state["column"], state["order"])
            proxy.sort(state["column"], state["order"])

    def _persist_sort():
        if table_key is None:
            return
        settings = load_settings()
        settings.setdefault("table_sort", {})[table_key] = {
            "column": state["column"],
            "order": "desc" if state["order"] == Qt.DescendingOrder else "asc",
        }
        save_settings(settings)

    def _on_section_clicked(column):
        if column == checkbox_column and on_toggle_all is not None:
            on_toggle_all()
            return
        if column not in sortable_columns:
            return
        if state["column"] == column and state["order"] == Qt.AscendingOrder:
            order = Qt.DescendingOrder
        else:
            order = Qt.AscendingOrder
        state["column"] = column
        state["order"] = order
        header.setSortIndicator(column, order)
        proxy.sort(column, order)
        _persist_sort()

    header.sectionClicked.connect(_on_section_clicked)


def install_column_width_persistence(view, table_key, checkbox_column=None):
    """Restores saved column widths for `table_key` and persists them on resize.

    The checkbox column (fixed-width) and the last column (stretched via
    `setStretchLastSection`) are excluded since their widths aren't
    meaningful to remember.
    """
    header = view.horizontalHeader()
    last_column = header.count() - 1

    def _skip(column):
        return column == checkbox_column or column == last_column

    saved_widths = load_settings().get("table_column_widths", {}).get(table_key, {})
    for column_str, width in saved_widths.items():
        column = int(column_str)
        if not _skip(column):
            header.resizeSection(column, width)

    def _on_section_resized(column, old_size, new_size):
        if _skip(column):
            return
        settings = load_settings()
        widths = settings.setdefault("table_column_widths", {}).setdefault(table_key, {})
        widths[str(column)] = new_size
        save_settings(settings)

    header.sectionResized.connect(_on_section_resized)

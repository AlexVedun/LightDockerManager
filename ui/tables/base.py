from PySide6.QtCore import QAbstractTableModel, QItemSelectionModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QStyledItemDelegate

from app_settings import load_settings, save_settings

GROUP_HEADER_BACKGROUND = QColor("#e3e8ec")


class DictRowsTableModel(QAbstractTableModel):
    """Generic table model over a list of dict rows.

    Column 0 is always a checkbox column (keyed by `row_key`) so several rows
    can be selected at once for a bulk action; the caller's `columns` /
    `accessors` describe the remaining, display-only columns.

    When `group_key` is given, rows are clustered under a group-header
    pseudo-row per distinct key (sorted with the falsy key, e.g. "", last),
    with a checkbox that selects/deselects every row in that group at once.
    `row_at` returns None for these header rows so callers already treating
    "no row" as "nothing actionable" need no changes.
    """

    CHECKBOX_COLUMN = 0

    def __init__(
        self,
        columns,
        accessors,
        row_key,
        color_column=None,
        color_getter=None,
        sort_accessors=None,
        group_key=None,
        group_label=None,
    ):
        super().__init__()
        self._columns = [""] + list(columns)
        self._accessors = accessors
        self._row_key = row_key
        self._color_column = None if color_column is None else color_column + 1
        self._color_getter = color_getter
        self._sort_accessors = sort_accessors or {}
        self._group_key = group_key
        self._group_label = group_label or (lambda key: key)
        self._checked = set()
        self._rows = []
        self._display = []
        self._groups = {}
        self._group_order = {}

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        live_keys = {self._row_key(row) for row in rows}
        self._checked &= live_keys
        self._rebuild_display()
        self.endResetModel()

    def _rebuild_display(self):
        if self._group_key is None:
            self._display = [("row", row) for row in self._rows]
            self._groups = {}
            self._group_order = {}
            return

        groups = {}
        for row in self._rows:
            groups.setdefault(self._group_key(row), []).append(row)
        ordered_keys = sorted(groups.keys(), key=lambda key: (not key, key))

        self._groups = groups
        self._group_order = {key: index for index, key in enumerate(ordered_keys)}
        display = []
        for key in ordered_keys:
            display.append(("group", key))
            for row in groups[key]:
                display.append(("row", row))
        self._display = display

    def row_at(self, row_index):
        kind, payload = self._display[row_index]
        return payload if kind == "row" else None

    def is_group_row(self, row_index):
        return self._display[row_index][0] == "group"

    def sort_key(self, row_index, column):
        """Sort key keeping groups contiguous and headers before their members.

        `column` (a display-column index, offset by the checkbox column)
        only affects ordering within a group of real rows.
        """
        kind, payload = self._display[row_index]
        if kind == "group":
            return (self._group_order.get(payload, 0), 0, None)
        group = self._group_key(payload) if self._group_key else None
        field_col = column - 1
        accessor = self._sort_accessors.get(field_col, self._accessors[field_col])
        return (self._group_order.get(group, 0), 1, accessor(payload))

    def rowCount(self, parent=QModelIndex()):
        return len(self._display)

    def columnCount(self, parent=QModelIndex()):
        return len(self._columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._columns[section]
        return None

    def flags(self, index):
        base = super().flags(index)
        if not index.isValid():
            return base
        kind, _ = self._display[index.row()]
        if kind == "group":
            return base & ~Qt.ItemIsSelectable
        return base

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        kind, payload = self._display[index.row()]
        col = index.column()

        if kind == "group":
            if role == Qt.BackgroundRole:
                return GROUP_HEADER_BACKGROUND
            if col == self.CHECKBOX_COLUMN:
                if role == Qt.CheckStateRole:
                    members = self._groups.get(payload, [])
                    if members and all(self._row_key(member) in self._checked for member in members):
                        return Qt.Checked
                    return Qt.Unchecked
                if role == Qt.DisplayRole:
                    return "  " + self._group_label(payload)
                if role == Qt.FontRole:
                    font = QFont()
                    font.setBold(True)
                    return font
            return None

        row = payload

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
        if role != Qt.CheckStateRole or index.column() != self.CHECKBOX_COLUMN:
            return False

        kind, payload = self._display[index.row()]
        if kind == "group":
            keys = {self._row_key(member) for member in self._groups.get(payload, [])}
            if value == Qt.Checked:
                self._checked |= keys
            else:
                self._checked -= keys
            top_left = self.index(0, self.CHECKBOX_COLUMN)
            bottom_right = self.index(self.rowCount() - 1, self.CHECKBOX_COLUMN)
            self.dataChanged.emit(top_left, bottom_right, [Qt.CheckStateRole])
            return True

        key = self._row_key(payload)
        if value == Qt.Checked:
            self._checked.add(key)
        else:
            self._checked.discard(key)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole])
        return True

    def checked_rows(self):
        return [row for row in self._rows if self._row_key(row) in self._checked]

    def has_checked(self):
        return bool(self._checked)

    def set_all_checked(self, checked):
        if not self._rows:
            return
        self._checked = {self._row_key(row) for row in self._rows} if checked else set()
        top_left = self.index(0, self.CHECKBOX_COLUMN)
        bottom_right = self.index(self.rowCount() - 1, self.CHECKBOX_COLUMN)
        self.dataChanged.emit(top_left, bottom_right, [Qt.CheckStateRole])


class GroupedSortProxyModel(QSortFilterProxyModel):
    """Sorts a grouped `DictRowsTableModel` by delegating to its `sort_key`.

    Keeps group headers and their members contiguous regardless of which
    column the user clicks to sort, since `sort_key` only lets the clicked
    column affect ordering within a group. Qt's descending mode is
    implemented by swapping the arguments given to `lessThan` (not by
    negating its result), so a plain tuple comparison would also reverse
    the group order itself; the group/header part is explicitly
    re-inverted here to cancel that out and keep it order-independent,
    while the in-group value naturally ends up following the requested
    direction.
    """

    def lessThan(self, left, right):
        model = self.sourceModel()
        left_group, left_header, left_value = model.sort_key(left.row(), left.column())
        right_group, right_header, right_value = model.sort_key(right.row(), right.column())
        descending = self.sortOrder() == Qt.DescendingOrder

        if left_group != right_group:
            result = left_group < right_group
            return not result if descending else result
        if left_header != right_header:
            result = left_header < right_header
            return not result if descending else result
        if left_value is None or right_value is None:
            return False
        return left_value < right_value


class _ForegroundPreservingDelegate(QStyledItemDelegate):
    """Makes a cell's Qt.ForegroundRole color survive row selection.

    Qt's item views normally swap the text color to the palette's
    HighlightedText role for a selected row, ignoring whatever a model
    returned for Qt.ForegroundRole - which is why a colored status dot
    (e.g. the running/paused indicator) turns plain white the moment its
    row gets selected. Forcing HighlightedText to match here keeps it its
    actual color regardless of selection.
    """

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        color = index.data(Qt.ForegroundRole)
        if color is not None:
            option.palette.setColor(QPalette.HighlightedText, color)


def install_foreground_color_delegate(view):
    """Keeps model-provided ForegroundRole colors visible even when a row is selected."""
    view.setItemDelegate(_ForegroundPreservingDelegate(view))


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


def install_selection_persistence(view, proxy, model, row_key):
    """Keeps the same logical row selected across `model.set_rows()` calls.

    A refresh replaces the model's row list wholesale (`beginResetModel` /
    `endResetModel`), which resets the view's selection as a side effect -
    so without this, the highlighted row would visibly jump away on every
    periodic/event-triggered refresh even though nothing the user cares
    about changed. Tracks the row by `row_key` (not position), so it
    survives the row moving to a different index across the refresh (e.g.
    due to sorting or other rows appearing/disappearing).
    """
    state = {"key": None}

    def _capture():
        indexes = view.selectionModel().selectedRows()
        if not indexes:
            state["key"] = None
            return
        row = model.row_at(proxy.mapToSource(indexes[0]).row())
        state["key"] = row_key(row) if row is not None else None

    def _restore():
        if state["key"] is None:
            return
        for proxy_row in range(proxy.rowCount()):
            source_row = proxy.mapToSource(proxy.index(proxy_row, 0)).row()
            row = model.row_at(source_row)
            if row is not None and row_key(row) == state["key"]:
                index = proxy.index(proxy_row, 0)
                view.selectionModel().select(
                    index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
                )
                view.selectionModel().setCurrentIndex(index, QItemSelectionModel.NoUpdate)
                return

    model.modelAboutToBeReset.connect(_capture)
    model.modelReset.connect(_restore)


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

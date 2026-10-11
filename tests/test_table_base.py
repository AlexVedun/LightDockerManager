from types import SimpleNamespace

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QTableView

import app_settings
from ui.tables.base import (
    DictRowsTableModel,
    install_column_sorting,
    install_column_width_persistence,
    install_row_context_menu,
)
from ui.tables.containers_table import ContainersTab

QApplication.instance() or QApplication([])


def _make_view():
    columns = ["Name", "Size"]
    accessors = [lambda r: r["name"], lambda r: r["size"]]
    model = DictRowsTableModel(columns, accessors, row_key=lambda r: r["name"])
    model.set_rows([{"name": "b", "size": 2}, {"name": "a", "size": 1}])
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setSortRole(Qt.UserRole)
    view = QTableView()
    view.setModel(proxy)
    view.horizontalHeader().setStretchLastSection(True)
    return view, proxy, model


def test_install_column_sorting_shows_indicator_and_sorts_on_click():
    view, proxy, model = _make_view()
    install_column_sorting(view, proxy, sortable_columns={1}, checkbox_column=model.CHECKBOX_COLUMN)

    assert view.horizontalHeader().isSortIndicatorShown()

    view.horizontalHeader().sectionClicked.emit(1)

    assert proxy.data(proxy.index(0, 1)) == "a"
    assert view.horizontalHeader().sortIndicatorOrder() == Qt.AscendingOrder


def test_install_column_sorting_persists_and_restores_sort_state(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_settings, "CONFIG_FILE", tmp_path / "settings.json")

    view, proxy, model = _make_view()
    install_column_sorting(view, proxy, sortable_columns={1}, checkbox_column=model.CHECKBOX_COLUMN, table_key="widgets")
    view.horizontalHeader().sectionClicked.emit(1)
    view.horizontalHeader().sectionClicked.emit(1)

    saved = app_settings.load_settings()["table_sort"]["widgets"]
    assert saved == {"column": 1, "order": "desc"}

    view2, proxy2, model2 = _make_view()
    install_column_sorting(view2, proxy2, sortable_columns={1}, checkbox_column=model2.CHECKBOX_COLUMN, table_key="widgets")

    assert view2.horizontalHeader().sortIndicatorOrder() == Qt.DescendingOrder
    assert proxy2.data(proxy2.index(0, 1)) == "b"


def test_install_column_width_persistence_restores_and_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_settings, "CONFIG_FILE", tmp_path / "settings.json")

    view, proxy, model = _make_view()
    install_column_width_persistence(view, "widgets", checkbox_column=model.CHECKBOX_COLUMN)
    view.horizontalHeader().resizeSection(1, 250)

    saved = app_settings.load_settings()["table_column_widths"]["widgets"]
    assert saved == {"1": 250}

    view2, proxy2, model2 = _make_view()
    install_column_width_persistence(view2, "widgets", checkbox_column=model2.CHECKBOX_COLUMN)

    assert view2.horizontalHeader().sectionSize(1) == 250


def test_install_column_width_persistence_skips_checkbox_and_last_column(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_settings, "CONFIG_FILE", tmp_path / "settings.json")

    view, proxy, model = _make_view()
    install_column_width_persistence(view, "widgets", checkbox_column=model.CHECKBOX_COLUMN)
    view.horizontalHeader().resizeSection(model.CHECKBOX_COLUMN, 5)
    last_column = view.horizontalHeader().count() - 1
    view.horizontalHeader().resizeSection(last_column, 999)

    settings = app_settings.load_settings()
    assert settings.get("table_column_widths", {}).get("widgets", {}) == {}


def test_context_menu_acts_on_clicked_row_even_when_another_is_checked(monkeypatch):
    view, proxy, model = _make_view()
    model.setData(model.index(0, 0), Qt.Checked, Qt.CheckStateRole)
    button = QPushButton("Remove")
    clicked_rows = []
    button.clicked.connect(lambda: clicked_rows.append(view.selectionModel().selectedRows()[0].row()))
    install_row_context_menu(view, proxy, model, (button,), lambda row, action: action())
    monkeypatch.setattr(QMenu, "popup", lambda menu, position: menu.actions()[0].trigger())
    view.resize(400, 200)
    view.show()
    QApplication.processEvents()

    position = view.visualRect(proxy.index(1, 1)).center()
    view.customContextMenuRequested.emit(position)

    assert clicked_rows == [1]
    assert [row["name"] for row in model.checked_rows()] == ["b"]


def test_context_action_ignores_bulk_checkboxes():
    tab = ContainersTab(SimpleNamespace(client=None))
    first = {"name": "first", "container": SimpleNamespace(id="first"), "project": "", "status": "running"}
    second = {"name": "second", "container": SimpleNamespace(id="second"), "project": "", "status": "running"}
    tab.model.set_rows([first, second])
    tab.model.setData(tab.model.index(1, 0), Qt.Checked, Qt.CheckStateRole)
    targets = []

    tab._run_context_action(first, lambda: targets.extend(tab._target_rows()))

    assert targets == [first]
    assert tab._context_row is None


def test_context_bulk_action_preserves_other_checked_rows(monkeypatch):
    tab = ContainersTab(SimpleNamespace(client=None))
    first = {"name": "first", "container": SimpleNamespace(id="first"), "project": "", "status": "running"}
    second = {"name": "second", "container": SimpleNamespace(id="second"), "project": "", "status": "running"}
    tab.model.set_rows([first, second])
    tab.model.setData(tab.model.index(2, 0), Qt.Checked, Qt.CheckStateRole)
    acted_on = []

    def run_bulk(owner, tasks, finished, track_action=False):
        for task in tasks:
            task()
        finished([], [])

    monkeypatch.setattr("ui.tables.containers_table.run_bulk_task", run_bulk)
    monkeypatch.setattr(tab, "refresh", lambda: None)
    tab._run_context_action(first, lambda: tab._run_bulk_action(lambda container: acted_on.append(container.id)))

    assert acted_on == ["first"]
    assert tab.model.checked_rows() == [second]

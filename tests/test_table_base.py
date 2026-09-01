from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtWidgets import QApplication, QTableView

import app_settings
from ui.tables.base import DictRowsTableModel, install_column_sorting, install_column_width_persistence

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

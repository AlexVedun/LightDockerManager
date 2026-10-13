from types import SimpleNamespace
import time

import pytest

from PySide6.QtWidgets import QApplication, QInputDialog

import app_settings
from ui.main_window import MainWindow
from version import __version__
from workers.task_worker import run_bulk_task

QApplication.instance() or QApplication([])


def test_window_title_includes_application_version(monkeypatch):
    monkeypatch.setattr("ui.main_window.load_profiles", lambda: [])
    manager = SimpleNamespace(client=None, mode=None, is_connected=lambda: False)
    window = MainWindow(manager)

    try:
        assert window.windowTitle() == f"LightDockerManager - {__version__}"
    finally:
        window.close()


def test_actions_use_fast_refresh_until_all_finish(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_settings, "CONFIG_FILE", tmp_path / "settings.json")
    app_settings.save_settings({"refresh_interval_seconds": 30})
    monkeypatch.setattr("ui.main_window.load_profiles", lambda: [])
    manager = SimpleNamespace(client=None, mode=None, is_connected=lambda: False)
    window = MainWindow(manager)
    refreshed = []
    monkeypatch.setattr(window, "_refresh_all", lambda: refreshed.append(True))

    try:
        assert window.refresh_timer.interval() == 30_000
        window.containers_tab.action_started.emit()
        window.images_tab.action_started.emit()
        assert window.refresh_timer.interval() == 5_000

        window.containers_tab.action_finished.emit()
        assert window.refresh_timer.interval() == 5_000
        window.images_tab.action_finished.emit()
        assert window.refresh_timer.interval() == 30_000
        assert len(refreshed) == 2
    finally:
        window.close()


def test_bulk_action_restores_configured_interval(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_settings, "CONFIG_FILE", tmp_path / "settings.json")
    app_settings.save_settings({"refresh_interval_seconds": 30})
    monkeypatch.setattr("ui.main_window.load_profiles", lambda: [])
    manager = SimpleNamespace(client=None, mode=None, is_connected=lambda: False)
    window = MainWindow(manager)

    try:
        run_bulk_task(window.containers_tab, [lambda: None, lambda: None], lambda errors, stale: None, track_action=True)
        assert window.refresh_timer.interval() == 5_000
        deadline = time.monotonic() + 2
        while window._active_actions and time.monotonic() < deadline:
            QApplication.processEvents()
        assert window._active_actions == 0
        assert window.refresh_timer.interval() == 30_000
    finally:
        window.close()


def test_action_restores_interval_even_when_immediate_refresh_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_settings, "CONFIG_FILE", tmp_path / "settings.json")
    app_settings.save_settings({"refresh_interval_seconds": 30})
    monkeypatch.setattr("ui.main_window.load_profiles", lambda: [])
    manager = SimpleNamespace(client=None, mode=None, is_connected=lambda: False)
    window = MainWindow(manager)

    def fail_refresh():
        raise RuntimeError("refresh failed")

    try:
        window._on_action_started()
        monkeypatch.setattr(window, "_refresh_all", fail_refresh)
        with pytest.raises(RuntimeError, match="refresh failed"):
            window._on_action_finished()
        assert window._active_actions == 0
        assert window.refresh_timer.interval() == 30_000
    finally:
        window.close()


def test_refresh_requested_during_inflight_refresh_runs_again(monkeypatch):
    from ui.tables.containers_table import ContainersTab

    manager = SimpleNamespace(client=None)
    tab = ContainersTab(manager)
    calls = []
    monkeypatch.setattr("ui.tables.containers_table.run_task", lambda *args, **kwargs: calls.append(kwargs))
    manager.client = object()

    tab.refresh()
    tab.refresh()
    assert len(calls) == 1

    tab._on_refresh_succeeded([])

    assert len(calls) == 2
    assert tab._refresh_queued is False


def test_refresh_setting_changed_during_action_applies_after_finish(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_settings, "CONFIG_FILE", tmp_path / "settings.json")
    app_settings.save_settings({"refresh_interval_seconds": 30})
    monkeypatch.setattr("ui.main_window.load_profiles", lambda: [])
    monkeypatch.setattr(QInputDialog, "getInt", lambda *args, **kwargs: (45, True))
    manager = SimpleNamespace(client=None, mode=None, is_connected=lambda: False)
    window = MainWindow(manager)

    try:
        window.containers_tab.action_started.emit()
        window._set_refresh_interval()
        assert window.refresh_timer.interval() == 5_000

        window.containers_tab.action_finished.emit()
        assert window.refresh_timer.interval() == 45_000
    finally:
        window.close()

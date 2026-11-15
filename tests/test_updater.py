import io
import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import updater
from ui.dialogs.update_dialog import UpdateDialog
from ui.main_window import MainWindow

QApplication.instance() or QApplication([])


def test_parse_version_and_is_newer_version():
    assert updater.parse_version("v1.2.4") == (1, 2, 4)
    assert updater.parse_version("1.10.0-beta1") == (1, 10, 0)
    assert updater.is_newer_version("1.2.5", "1.2.4") is True
    assert updater.is_newer_version("v1.3.0", "1.2.4") is True
    assert updater.is_newer_version("1.2.4", "1.2.4") is False
    assert updater.is_newer_version("1.2.3", "1.2.4") is False


def test_select_asset_for_platform():
    assets = [
        {"name": "LightDockerManager-1.3.0-x86_64.AppImage", "browser_download_url": "https://example.com/a.AppImage", "size": 100},
        {"name": "LightDockerManager-1.3.0-arm64.dmg", "browser_download_url": "https://example.com/a.dmg", "size": 200},
        {"name": "LightDockerManager-1.3.0-x86_64.exe", "browser_download_url": "https://example.com/a.exe", "size": 300},
    ]

    assert updater.select_asset_for_platform(assets, "linux")["name"].endswith(".AppImage")
    assert updater.select_asset_for_platform(assets, "darwin")["name"].endswith(".dmg")
    assert updater.select_asset_for_platform(assets, "win32")["name"].endswith(".exe")
    assert updater.select_asset_for_platform(assets, "freebsd") is None


def test_check_for_updates_returns_release_info_when_newer(monkeypatch):
    payload = {
        "tag_name": "v2.0.0",
        "body": "Major update",
        "html_url": "https://github.com/AlexVedun/LightDockerManager/releases/tag/v2.0.0",
        "assets": [
            {
                "name": "LightDockerManager-2.0.0-arm64.dmg",
                "browser_download_url": "https://example.com/LightDockerManager-2.0.0-arm64.dmg",
                "size": 12345,
            }
        ],
    }

    class DummyResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda req, timeout=15: DummyResponse(json.dumps(payload).encode("utf-8")),
    )

    info = updater.check_for_updates(current_version="1.2.4", platform="darwin")
    assert info == {
        "version": "2.0.0",
        "tag_name": "v2.0.0",
        "body": "Major update",
        "html_url": "https://github.com/AlexVedun/LightDockerManager/releases/tag/v2.0.0",
        "asset": {
            "name": "LightDockerManager-2.0.0-arm64.dmg",
            "url": "https://example.com/LightDockerManager-2.0.0-arm64.dmg",
            "size": 12345,
        },
    }


def test_check_for_updates_returns_none_when_up_to_date(monkeypatch):
    payload = {"tag_name": "1.2.4", "assets": []}

    class DummyResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        updater.urllib.request,
        "urlopen",
        lambda req, timeout=15: DummyResponse(json.dumps(payload).encode("utf-8")),
    )

    assert updater.check_for_updates(current_version="1.2.4", platform="linux") is None


def test_download_release_asset_writes_file_and_reports_progress(tmp_path, monkeypatch):
    data = b"hello world" * 100

    class DummyResponse(io.BytesIO):
        headers = {"Content-Length": str(len(data))}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda req, timeout=15: DummyResponse(data))

    progress_calls = []
    dest = tmp_path / "update.bin"
    result = updater.download_release_asset("https://example.com/update.bin", dest, progress=lambda d, t: progress_calls.append((d, t)))

    assert result == dest
    assert dest.read_bytes() == data
    assert progress_calls[-1] == (len(data), len(data))


def test_can_self_update_across_platforms(tmp_path):
    assert updater.can_self_update(platform="linux", env={"APPIMAGE": "/tmp/app.AppImage"}, frozen=True) is True
    assert updater.can_self_update(platform="linux", env={}, frozen=True) is False

    app_exe = tmp_path / "LightDockerManager.app" / "Contents" / "MacOS" / "LightDockerManager"
    app_exe.parent.mkdir(parents=True)
    app_exe.write_text("bin")
    assert updater.can_self_update(platform="darwin", frozen=True, executable_path=app_exe) is True
    assert updater.can_self_update(platform="darwin", frozen=False, executable_path=app_exe) is False

    assert updater.can_self_update(platform="win32", frozen=True) is True
    assert updater.can_self_update(platform="win32", frozen=False) is False


def test_apply_linux_appimage_update_replaces_and_relaunches(tmp_path, monkeypatch):
    appimage = tmp_path / "LightDockerManager.AppImage"
    appimage.write_bytes(b"old")
    downloaded = tmp_path / "downloaded.AppImage"
    downloaded.write_bytes(b"new-binary")

    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kwargs: launched.append(args))

    updater.apply_linux_appimage_update(downloaded, appimage_path=appimage)

    assert appimage.read_bytes() == b"new-binary"
    assert appimage.stat().st_mode & 0o111
    assert launched == [[str(appimage)]]


def test_apply_macos_dmg_update_creates_script_with_xattr_and_codesign(tmp_path, monkeypatch):
    app_bundle = tmp_path / "LightDockerManager.app"
    app_bundle.mkdir()
    dmg_file = tmp_path / "update.dmg"
    dmg_file.write_bytes(b"dmg")

    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kwargs: launched.append(args))

    updater.apply_macos_dmg_update(dmg_file, app_bundle_path=app_bundle, current_pid=99999)

    assert len(launched) == 1
    assert launched[0][0] == "/bin/bash"
    script_path = launched[0][1]
    script_text = open(script_path, encoding="utf-8").read()
    assert "xattr -cr" in script_text
    assert "codesign --force --deep --sign -" in script_text
    assert str(app_bundle) in script_text


def test_apply_windows_exe_update_creates_batch_and_spawns_cmd(tmp_path, monkeypatch):
    exe_file = tmp_path / "LightDockerManager.exe"
    exe_file.write_bytes(b"old-exe")
    downloaded = tmp_path / "downloaded.exe"
    downloaded.write_bytes(b"new-exe")

    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kwargs: launched.append(args))

    updater.apply_windows_exe_update(downloaded, executable_path=exe_file, current_pid=4242)

    staged = tmp_path / "LightDockerManager.new.exe"
    assert staged.read_bytes() == b"new-exe"
    assert len(launched) == 1
    assert launched[0][:2] == ["cmd.exe", "/c"]


def test_update_dialog_hides_self_update_button_when_not_supported(monkeypatch):
    monkeypatch.setattr("ui.dialogs.update_dialog.can_self_update", lambda: False)
    release_info = {
        "version": "2.0.0",
        "tag_name": "v2.0.0",
        "body": "Notes",
        "html_url": "https://example.com/release",
        "asset": {"name": "a.dmg", "url": "https://example.com/a.dmg", "size": 100},
    }
    dialog = UpdateDialog(release_info)
    try:
        assert dialog.btn_update.isHidden() is True
        assert dialog.btn_open_page.isHidden() is False
    finally:
        dialog.close()


def test_main_window_manual_update_check_shows_up_to_date_message(monkeypatch):
    monkeypatch.setattr("ui.main_window.load_profiles", lambda: [])
    info_calls = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: info_calls.append(args))
    manager = SimpleNamespace(client=None, mode=None, is_connected=lambda: False)
    window = MainWindow(manager)
    try:
        window._on_update_check_succeeded(None, manual=True)
        assert len(info_calls) == 1
    finally:
        window.close()

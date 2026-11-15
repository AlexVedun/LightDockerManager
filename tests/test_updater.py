import http.client
import io
import json
import os
import subprocess
from pathlib import Path
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


def test_download_release_asset_raises_on_incomplete_read_and_removes_partial_file(tmp_path, monkeypatch):
    partial_data = b"short"

    class DummyResponse(io.BytesIO):
        headers = {"Content-Length": "100"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda req, timeout=15: DummyResponse(partial_data))

    dest = tmp_path / "update.bin"
    with pytest.raises(http.client.IncompleteRead) as exc_info:
        updater.download_release_asset("https://example.com/update.bin", dest)

    assert exc_info.value.partial == len(partial_data)
    assert exc_info.value.expected == 100 - len(partial_data)
    assert not dest.exists()


def test_download_release_asset_verifies_expected_size_when_header_missing(tmp_path, monkeypatch):
    partial_data = b"short"

    class DummyResponse(io.BytesIO):
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda req, timeout=15: DummyResponse(partial_data))

    dest = tmp_path / "update.bin"
    with pytest.raises(http.client.IncompleteRead):
        updater.download_release_asset("https://example.com/update.bin", dest, expected_size=50)

    assert not dest.exists()


def test_can_self_update_across_platforms(tmp_path, monkeypatch):
    assert updater.can_self_update(platform="linux", env={"APPIMAGE": "/tmp/app.AppImage"}, frozen=True) is True
    assert updater.can_self_update(platform="linux", env={}, frozen=True) is False

    app_exe = tmp_path / "LightDockerManager.app" / "Contents" / "MacOS" / "LightDockerManager"
    app_exe.parent.mkdir(parents=True)
    app_exe.write_text("bin")
    assert updater.can_self_update(platform="darwin", frozen=True, executable_path=app_exe) is True
    assert updater.can_self_update(platform="darwin", frozen=False, executable_path=app_exe) is False

    monkeypatch.setattr(
        Path,
        "resolve",
        lambda self: Path("/Volumes/LightDockerManager/LightDockerManager.app/Contents/MacOS/LightDockerManager"),
    )
    assert updater.can_self_update(platform="darwin", frozen=True, executable_path=app_exe) is False
    monkeypatch.undo()

    monkeypatch.setattr(os, "statvfs", lambda path: SimpleNamespace(f_flag=getattr(os, "ST_RDONLY", 1)))
    assert updater.can_self_update(platform="darwin", frozen=True, executable_path=app_exe) is False
    monkeypatch.undo()

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


def _make_fake_macos_tools(bin_dir, *, ditto_fails=False, empty_dmg=False):
    bin_dir.mkdir(parents=True, exist_ok=True)

    hdiutil = bin_dir / "hdiutil"
    if empty_dmg:
        hdiutil.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    else:
        hdiutil.write_text(
            '#!/bin/bash\n'
            'if [ "$1" = "attach" ]; then\n'
            '  for ((i=1; i<=$#; i++)); do\n'
            '    if [ "${!i}" = "-mountpoint" ]; then\n'
            '      next=$((i+1))\n'
            '      mp="${!next}"\n'
            '      mkdir -p "$mp/LightDockerManager.app"\n'
            '      echo "new-version" > "$mp/LightDockerManager.app/version.txt"\n'
            '    fi\n'
            '  done\n'
            'fi\n'
            'exit 0\n',
            encoding="utf-8",
        )
    hdiutil.chmod(0o755)

    ditto = bin_dir / "ditto"
    if ditto_fails:
        ditto.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    else:
        ditto.write_text('#!/bin/bash\ncp -R "$1" "$2"\n', encoding="utf-8")
    ditto.chmod(0o755)

    for tool in ("xattr", "codesign", "open"):
        p = bin_dir / tool
        p.write_text('#!/bin/bash\necho "$0 $@" >> "' + str(bin_dir / "calls.log") + '"\nexit 0\n', encoding="utf-8")
        p.chmod(0o755)


def test_macos_update_script_execution_replaces_bundle_safely(tmp_path, monkeypatch):
    app_bundle = tmp_path / "LightDockerManager.app"
    app_bundle.mkdir()
    (app_bundle / "version.txt").write_text("old-version", encoding="utf-8")
    dmg_file = tmp_path / "update.dmg"
    dmg_file.write_bytes(b"dmg")

    bin_dir = tmp_path / "fake_bin"
    _make_fake_macos_tools(bin_dir)

    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kwargs: launched.append(args))
    updater.apply_macos_dmg_update(dmg_file, app_bundle_path=app_bundle, current_pid=999999)
    monkeypatch.undo()

    script_path = launched[0][1]
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    res = subprocess.run(["/bin/bash", script_path], env=env, capture_output=True, text=True)

    assert res.returncode == 0
    assert (app_bundle / "version.txt").read_text(encoding="utf-8").strip() == "new-version"
    assert not app_bundle.with_name(".LightDockerManager.app.new").exists()
    assert not app_bundle.with_name(".LightDockerManager.app.bak").exists()


def test_macos_update_script_preserves_existing_app_when_dmg_has_no_app(tmp_path, monkeypatch):
    app_bundle = tmp_path / "LightDockerManager.app"
    app_bundle.mkdir()
    (app_bundle / "version.txt").write_text("old-version", encoding="utf-8")
    dmg_file = tmp_path / "update.dmg"
    dmg_file.write_bytes(b"dmg")

    bin_dir = tmp_path / "fake_bin"
    _make_fake_macos_tools(bin_dir, empty_dmg=True)

    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kwargs: launched.append(args))
    updater.apply_macos_dmg_update(dmg_file, app_bundle_path=app_bundle, current_pid=999999)
    monkeypatch.undo()

    script_path = launched[0][1]
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    res = subprocess.run(["/bin/bash", script_path], env=env, capture_output=True, text=True)

    assert res.returncode == 1
    assert app_bundle.exists()
    assert (app_bundle / "version.txt").read_text(encoding="utf-8") == "old-version"


def test_macos_update_script_preserves_existing_app_when_ditto_fails(tmp_path, monkeypatch):
    app_bundle = tmp_path / "LightDockerManager.app"
    app_bundle.mkdir()
    (app_bundle / "version.txt").write_text("old-version", encoding="utf-8")
    dmg_file = tmp_path / "update.dmg"
    dmg_file.write_bytes(b"dmg")

    bin_dir = tmp_path / "fake_bin"
    _make_fake_macos_tools(bin_dir, ditto_fails=True)

    launched = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kwargs: launched.append(args))
    updater.apply_macos_dmg_update(dmg_file, app_bundle_path=app_bundle, current_pid=999999)
    monkeypatch.undo()

    script_path = launched[0][1]
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
    subprocess.run(["/bin/bash", script_path], env=env, capture_output=True, text=True)

    assert app_bundle.exists()
    assert (app_bundle / "version.txt").read_text(encoding="utf-8") == "old-version"


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

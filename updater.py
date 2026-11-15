import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from version import __version__

GITHUB_REPO = "AlexVedun/LightDockerManager"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
REQUEST_TIMEOUT_SECONDS = 15
DOWNLOAD_CHUNK_SIZE = 64 * 1024


def parse_version(version_str):
    cleaned = str(version_str).strip().lstrip("vV")
    parts = []
    for segment in cleaned.split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer_version(latest_version, current_version=__version__):
    return parse_version(latest_version) > parse_version(current_version)


def expected_asset_suffix(platform=None):
    platform = platform or sys.platform
    if platform.startswith("linux"):
        return ".AppImage"
    if platform == "darwin":
        return ".dmg"
    if platform in ("win32", "cygwin"):
        return ".exe"
    return None


def select_asset_for_platform(assets, platform=None):
    suffix = expected_asset_suffix(platform)
    if not suffix:
        return None
    for asset in assets or []:
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        if name.endswith(suffix) and url:
            return {
                "name": name,
                "url": url,
                "size": asset.get("size") or 0,
            }
    return None


def check_for_updates(current_version=__version__, platform=None):
    request = urllib.request.Request(
        LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"LightDockerManager/{current_version}",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))

    tag_name = (payload.get("tag_name") or "").strip()
    latest_version = tag_name.lstrip("vV")
    if not latest_version or not is_newer_version(latest_version, current_version):
        return None

    asset = select_asset_for_platform(payload.get("assets", []), platform=platform)
    return {
        "version": latest_version,
        "tag_name": tag_name,
        "body": payload.get("body") or "",
        "html_url": payload.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest",
        "asset": asset,
    }


def download_release_asset(url, destination_path, progress=None):
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"LightDockerManager/{__version__}"},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        content_length = response.headers.get("Content-Length")
        total = int(content_length) if content_length and content_length.isdigit() else None
        transferred = 0
        with destination.open("wb") as out_file:
            while True:
                chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                out_file.write(chunk)
                transferred += len(chunk)
                if progress is not None:
                    progress(transferred, total)
    return destination


def resolve_macos_app_bundle(executable_path=None):
    path = Path(executable_path or sys.executable).resolve()
    for parent in (path, *path.parents):
        if parent.suffix == ".app":
            return parent
    return None


def can_self_update(platform=None, env=None, frozen=None, executable_path=None):
    platform = platform or sys.platform
    env = os.environ if env is None else env
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen

    if platform.startswith("linux"):
        return bool(env.get("APPIMAGE"))
    if platform == "darwin":
        return bool(frozen and resolve_macos_app_bundle(executable_path) is not None)
    if platform in ("win32", "cygwin"):
        return bool(frozen)
    return False


def apply_linux_appimage_update(downloaded_file, appimage_path=None):
    target = Path(appimage_path or os.environ.get("APPIMAGE", "")).resolve()
    if not str(target) or not target.exists():
        raise RuntimeError("APPIMAGE path is not available.")

    staged = target.with_name(f".{target.name}.new")
    shutil.move(str(downloaded_file), str(staged))
    current_mode = staged.stat().st_mode
    staged.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(staged, target)
    subprocess.Popen([str(target)], close_fds=True, start_new_session=True)


def apply_windows_exe_update(downloaded_file, executable_path=None, current_pid=None):
    target = Path(executable_path or sys.executable).resolve()
    pid = current_pid or os.getpid()
    staged = target.with_name(f"{target.stem}.new{target.suffix}")
    shutil.move(str(downloaded_file), str(staged))

    script_file = Path(tempfile.gettempdir()) / f"ldm_update_{pid}.cmd"
    script_content = (
        "@echo off\r\n"
        ":waitloop\r\n"
        f'tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL\r\n'
        "if not errorlevel 1 (\r\n"
        "    timeout /t 1 /nobreak >NUL\r\n"
        "    goto waitloop\r\n"
        ")\r\n"
        f'move /Y "{staged}" "{target}" >NUL\r\n'
        f'start "" "{target}"\r\n'
        'del "%~f0"\r\n'
    )
    script_file.write_text(script_content, encoding="utf-8")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(["cmd.exe", "/c", str(script_file)], creationflags=creationflags, close_fds=True)


def apply_macos_dmg_update(downloaded_file, app_bundle_path=None, current_pid=None):
    app_bundle = Path(app_bundle_path) if app_bundle_path else resolve_macos_app_bundle()
    if app_bundle is None:
        raise RuntimeError("Could not locate the running .app bundle.")

    pid = current_pid or os.getpid()
    dmg_path = Path(downloaded_file).resolve()
    mount_dir = Path(tempfile.mkdtemp(prefix="ldm_dmg_"))
    script_file = Path(tempfile.gettempdir()) / f"ldm_update_{pid}.sh"
    app_name = app_bundle.name

    script_content = f"""#!/bin/bash
set -e
while kill -0 {pid} 2>/dev/null; do
    sleep 0.5
done

cleanup() {{
    hdiutil detach "{mount_dir}" -force -quiet 2>/dev/null || true
    rm -rf "{mount_dir}" "{dmg_path}" "$0"
}}
trap cleanup EXIT

hdiutil attach "{dmg_path}" -nobrowse -readonly -mountpoint "{mount_dir}" -quiet
SRC_APP="{mount_dir}/{app_name}"
if [ ! -d "$SRC_APP" ]; then
    SRC_APP="$(find "{mount_dir}" -maxdepth 2 -name "*.app" -print -quit)"
fi

if [ -w "{app_bundle.parent}" ] && ( [ ! -e "{app_bundle}" ] || [ -w "{app_bundle}" ] ); then
    rm -rf "{app_bundle}"
    ditto "$SRC_APP" "{app_bundle}"
    xattr -cr "{app_bundle}" 2>/dev/null || true
    codesign --force --deep --sign - "{app_bundle}" 2>/dev/null || true
else
    osascript -e 'do shell script "rm -rf \\"{app_bundle}\\" && ditto \\"'"$SRC_APP"'\\" \\"{app_bundle}\\" && xattr -cr \\"{app_bundle}\\" && (codesign --force --deep --sign - \\"{app_bundle}\\" || true)" with administrator privileges'
fi

open -n "{app_bundle}"
"""
    script_file.write_text(script_content, encoding="utf-8")
    script_file.chmod(0o755)
    subprocess.Popen(["/bin/bash", str(script_file)], close_fds=True, start_new_session=True)


def download_and_install_update(release_info, progress=None, platform=None):
    platform = platform or sys.platform
    asset = release_info.get("asset")
    if not asset or not asset.get("url"):
        raise RuntimeError("No compatible installer asset found for this platform.")

    suffix = Path(asset["name"]).suffix
    fd, temp_path = tempfile.mkstemp(prefix="ldm_update_", suffix=suffix)
    os.close(fd)
    downloaded = Path(temp_path)
    try:
        download_release_asset(asset["url"], downloaded, progress=progress)
        if platform.startswith("linux"):
            apply_linux_appimage_update(downloaded)
        elif platform == "darwin":
            apply_macos_dmg_update(downloaded)
        elif platform in ("win32", "cygwin"):
            apply_windows_exe_update(downloaded)
        else:
            raise RuntimeError(f"Unsupported platform: {platform}")
    except Exception:
        downloaded.unlink(missing_ok=True)
        raise

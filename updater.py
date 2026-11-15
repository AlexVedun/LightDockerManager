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


def download_release_asset(url, destination_path, progress=None, expected_size=None):
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"LightDockerManager/{__version__}"},
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        resp_headers = getattr(response, "headers", None) or {}
        content_length = resp_headers.get("Content-Length") if hasattr(resp_headers, "get") else None
        header_total = int(content_length) if content_length and str(content_length).isdigit() else None
        asset_total = int(expected_size) if expected_size and expected_size > 0 else None
        if header_total is not None and asset_total is not None:
            total = max(header_total, asset_total)
        else:
            total = header_total if header_total is not None else asset_total
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
        if total is not None and transferred < total:
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"Incomplete download: received {transferred} of {total} bytes.")
    return destination


def resolve_macos_app_bundle(executable_path=None):
    path = Path(executable_path or sys.executable).resolve()
    for parent in (path, *path.parents):
        if parent.suffix == ".app":
            return parent
    return None


def _is_macos_bundle_updatable(app_bundle):
    parts = app_bundle.parts
    if len(parts) >= 2 and parts[0] == "/" and parts[1] == "Volumes":
        return False
    st_vfs = getattr(os, "statvfs", None)
    if st_vfs is not None:
        try:
            vfs = st_vfs(app_bundle.parent)
            st_rdonly = getattr(os, "ST_RDONLY", 1)
            if bool(vfs.f_flag & st_rdonly):
                return False
        except OSError:
            return False
    return True


def can_self_update(platform=None, env=None, frozen=None, executable_path=None):
    platform = platform or sys.platform
    env = os.environ if env is None else env
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen

    if platform.startswith("linux"):
        return bool(env.get("APPIMAGE"))
    if platform == "darwin":
        if not frozen:
            return False
        app_bundle = resolve_macos_app_bundle(executable_path)
        return app_bundle is not None and _is_macos_bundle_updatable(app_bundle)
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
        f'if exist "{staged}" (\r\n'
        f'    move /Y "{staged}" "{target}" >NUL\r\n'
        ")\r\n"
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
    if not _is_macos_bundle_updatable(app_bundle):
        raise RuntimeError("Cannot self-update an application running from a read-only volume.")

    pid = current_pid or os.getpid()
    dmg_path = Path(downloaded_file).resolve()
    mount_dir = Path(tempfile.mkdtemp(prefix="ldm_dmg_"))
    script_file = Path(tempfile.gettempdir()) / f"ldm_update_{pid}.sh"
    app_name = app_bundle.name
    staged_bundle = app_bundle.with_name(f".{app_name}.new")
    backup_bundle = app_bundle.with_name(f".{app_name}.bak")

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
if [ -z "$SRC_APP" ] || [ ! -d "$SRC_APP" ]; then
    open -n "{app_bundle}"
    exit 1
fi

install_direct() {{
    rm -rf "{staged_bundle}" "{backup_bundle}"
    if ! ditto "$SRC_APP" "{staged_bundle}"; then
        rm -rf "{staged_bundle}"
        return 1
    fi
    xattr -cr "{staged_bundle}" 2>/dev/null || true
    codesign --force --deep --sign - "{staged_bundle}" 2>/dev/null || true
    if [ -d "{app_bundle}" ]; then
        if ! mv "{app_bundle}" "{backup_bundle}"; then
            rm -rf "{staged_bundle}"
            return 1
        fi
    fi
    if mv "{staged_bundle}" "{app_bundle}"; then
        rm -rf "{backup_bundle}"
    else
        if [ -d "{backup_bundle}" ] && [ ! -d "{app_bundle}" ]; then
            mv "{backup_bundle}" "{app_bundle}"
        fi
        rm -rf "{staged_bundle}"
        return 1
    fi
}}

if [ -w "{app_bundle.parent}" ] && ( [ ! -e "{app_bundle}" ] || [ -w "{app_bundle}" ] ); then
    install_direct || true
else
    osascript -e 'do shell script "rm -rf \\"{staged_bundle}\\" \\"{backup_bundle}\\" && if ! ditto \\"'"$SRC_APP"'\\" \\"{staged_bundle}\\"; then rm -rf \\"{staged_bundle}\\"; exit 1; fi && (xattr -cr \\"{staged_bundle}\\" || true) && (codesign --force --deep --sign - \\"{staged_bundle}\\" || true) && (if [ -d \\"{app_bundle}\\" ]; then if ! mv \\"{app_bundle}\\" \\"{backup_bundle}\\"; then rm -rf \\"{staged_bundle}\\"; exit 1; fi; fi) && (if mv \\"{staged_bundle}\\" \\"{app_bundle}\\"; then rm -rf \\"{backup_bundle}\\"; else if [ -d \\"{backup_bundle}\\" ] && [ ! -d \\"{app_bundle}\\" ]; then mv \\"{backup_bundle}\\" \\"{app_bundle}\\"; fi; rm -rf \\"{staged_bundle}\\"; exit 1; fi)" with administrator privileges' || true
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
        download_release_asset(
            asset["url"],
            downloaded,
            progress=progress,
            expected_size=asset.get("size"),
        )
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

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

PYTHON="${PYTHON:-python3}"
VERSION="${VERSION:-$("$PYTHON" -c 'from version import __version__; print(__version__)')}"
VERSION="${VERSION#v}"
ARCH_LABEL="${ARCH_LABEL:-$(uname -m)}"

DIST_DIR="$PROJECT_ROOT/distribution"
TEMP_DIR="$(mktemp -d)"
ICONSET_DIR="$TEMP_DIR/LightDockerManager.iconset"
ICNS_FILE="$TEMP_DIR/LightDockerManager.icns"
DMG_ROOT="$TEMP_DIR/dmg-root"
OUTPUT_FILE="$DIST_DIR/LightDockerManager-$VERSION-$ARCH_LABEL.dmg"

cleanup() {
    rm -rf "$TEMP_DIR" "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist"
}
trap cleanup EXIT

mkdir -p "$DIST_DIR" "$DMG_ROOT"

"$PYTHON" packaging/create_icns.py packaging/icon.svg "$ICONSET_DIR"
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_FILE"

"$PYTHON" -m PyInstaller \
    --name LightDockerManager \
    --windowed \
    --noconfirm \
    --clean \
    --icon "$ICNS_FILE" \
    --osx-bundle-identifier com.alexvedun.lightdockermanager \
    --add-data "i18n:i18n" \
    --add-data "packaging/icon.png:packaging" \
    main.py

cp -R dist/LightDockerManager.app "$DMG_ROOT/"
ln -s /Applications "$DMG_ROOT/Applications"
rm -f "$OUTPUT_FILE"
hdiutil create \
    -volname "LightDockerManager" \
    -srcfolder "$DMG_ROOT" \
    -ov \
    -format UDZO \
    "$OUTPUT_FILE"

echo "Built: $OUTPUT_FILE"

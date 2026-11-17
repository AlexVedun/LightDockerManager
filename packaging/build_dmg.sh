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
ICNS_FILE="$TEMP_DIR/AppIcon.icns"
ICON_BUNDLE="$TEMP_DIR/AppIcon.icon"
CATALOG_DIR="$TEMP_DIR/Assets.xcassets"
COMPILED_ICONS="$TEMP_DIR/compiled-icons"
BUNDLE_ID=com.alexvedun.lightdockermanager
DMG_ROOT="$TEMP_DIR/dmg-root"
OUTPUT_FILE="$DIST_DIR/LightDockerManager-$VERSION-$ARCH_LABEL.dmg"

cleanup() {
    rm -rf "$TEMP_DIR" "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist"
}
trap cleanup EXIT

mkdir -p "$DIST_DIR" "$DMG_ROOT" "$CATALOG_DIR" "$COMPILED_ICONS"

cp -R packaging/macos/AppIcon.icon "$ICON_BUNDLE"
"$PYTHON" packaging/create_icns.py packaging/icon.svg "$ICONSET_DIR" \
    --foreground "$ICON_BUNDLE/Assets/Foreground.png"
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_FILE"
printf '%s\n' '{"info":{"author":"xcode","version":1}}' > "$CATALOG_DIR/Contents.json"
xcrun --sdk macosx actool "$CATALOG_DIR" "$ICON_BUNDLE" \
    --compile "$COMPILED_ICONS" \
    --app-icon AppIcon \
    --target-device mac \
    --platform macosx \
    --minimum-deployment-target 26.0 \
    --bundle-identifier "$BUNDLE_ID" \
    --output-partial-info-plist "$TEMP_DIR/icon-info.plist"

"$PYTHON" -m PyInstaller \
    --name LightDockerManager \
    --windowed \
    --noconfirm \
    --clean \
    --icon "$ICNS_FILE" \
    --osx-bundle-identifier "$BUNDLE_ID" \
    --add-data "i18n:i18n" \
    main.py

APP_BUNDLE="dist/LightDockerManager.app"
cp "$COMPILED_ICONS/Assets.car" "$APP_BUNDLE/Contents/Resources/"
/usr/libexec/PlistBuddy -c "Add :CFBundleIconName string AppIcon" "$APP_BUNDLE/Contents/Info.plist"
# Refresh PyInstaller's ad hoc signature after changing the bundle resources.
codesign --force --sign - "$APP_BUNDLE"
codesign --verify --deep --strict "$APP_BUNDLE"

cp -R "$APP_BUNDLE" "$DMG_ROOT/"
ln -s /Applications "$DMG_ROOT/Applications"
rm -f "$OUTPUT_FILE"
hdiutil create \
    -volname "LightDockerManager" \
    -srcfolder "$DMG_ROOT" \
    -ov \
    -format UDZO \
    "$OUTPUT_FILE"

echo "Built: $OUTPUT_FILE"

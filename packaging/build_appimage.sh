#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

PYTHON="${PYTHON:-.venv/bin/python}"

resolve_appimagetool() {
    if [ -n "${APPIMAGETOOL:-}" ]; then
        echo "$APPIMAGETOOL"
        return
    fi
    if command -v appimagetool >/dev/null 2>&1; then
        command -v appimagetool
        return
    fi
    for candidate in "$HOME/appimagetool.AppImage" "$HOME/Applications/appimagetool.AppImage" "/opt/appimagetool/appimagetool.AppImage"; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return
        fi
    done
    echo ""
}

APPIMAGETOOL="$(resolve_appimagetool)"
if [ -z "$APPIMAGETOOL" ]; then
    echo "appimagetool not found." >&2
    echo "Install it, add it to PATH, or set APPIMAGETOOL=/path/to/appimagetool.AppImage" >&2
    exit 1
fi
echo "Using appimagetool: $APPIMAGETOOL"

DIST_DIR="$PROJECT_ROOT/distribution"

rm -rf build dist AppDir "$DIST_DIR"
mkdir -p "$DIST_DIR"

"$PYTHON" -m PyInstaller \
    --name LightDockerManager \
    --windowed \
    --noconfirm \
    --add-data "i18n:i18n" \
    main.py

mkdir -p AppDir
cp -r dist/LightDockerManager/. AppDir/
cp packaging/lightdockermanager.desktop AppDir/lightdockermanager.desktop
cp packaging/icon.png AppDir/lightdockermanager.png

cat > AppDir/AppRun <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/LightDockerManager" "$@"
EOF
chmod +x AppDir/AppRun

"$APPIMAGETOOL" AppDir "$DIST_DIR/LightDockerManager-x86_64.AppImage"
rm -rf build dist AppDir

echo "Built: $DIST_DIR/LightDockerManager-x86_64.AppImage"

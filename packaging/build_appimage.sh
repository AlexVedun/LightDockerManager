#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

APPIMAGETOOL="${APPIMAGETOOL:-appimagetool}"
PYTHON="${PYTHON:-.venv/bin/python}"

rm -rf build dist AppDir

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

"$APPIMAGETOOL" AppDir "$PROJECT_ROOT/LightDockerManager-x86_64.AppImage"

echo "Built: $PROJECT_ROOT/LightDockerManager-x86_64.AppImage"

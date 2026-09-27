import argparse
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ICON_FILES = (
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
)


def render_iconset(source, output_dir):
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise ValueError(f"Could not load SVG icon: {source}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for size, file_name in ICON_FILES:
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        if not image.save(str(output_dir / file_name)):
            raise RuntimeError(f"Could not write icon: {file_name}")


def main():
    parser = argparse.ArgumentParser(description="Render an SVG as a macOS .iconset directory.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    render_iconset(args.source, args.output_dir)


if __name__ == "__main__":
    main()

import argparse
from pathlib import Path
from xml.etree import ElementTree

from PySide6.QtCore import QByteArray, QRectF, Qt
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


def render_png(renderer, size, bounds, destination):
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter, bounds)
    painter.end()
    if not image.save(str(destination)):
        raise RuntimeError(f"Could not write icon: {destination}")


def render_iconset(source, output_dir):
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise ValueError(f"Could not load SVG icon: {source}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for size, file_name in ICON_FILES:
        # Leave transparent margins around the tile at every resolution.
        inset = size * 0.1
        render_png(renderer, size, QRectF(inset, inset, size * 0.8, size * 0.8), output_dir / file_name)


def render_icon_composer_layer(source, destination):
    svg = ElementTree.parse(source).getroot()
    namespace = "http://www.w3.org/2000/svg"
    ElementTree.register_namespace("", namespace)
    for background in svg.findall(f"{{{namespace}}}rect"):
        svg.remove(background)
    renderer = QSvgRenderer(QByteArray(ElementTree.tostring(svg)))
    if not renderer.isValid():
        raise ValueError(f"Could not load SVG foreground: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Center the artwork inside the mask supplied by macOS.
    render_png(renderer, 1024, QRectF(166, 55, 740, 740), destination)


def main():
    parser = argparse.ArgumentParser(description="Render an SVG as a macOS .iconset directory.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--foreground", type=Path, help="Also render a transparent Icon Composer layer.")
    args = parser.parse_args()
    render_iconset(args.source, args.output_dir)
    if args.foreground is not None:
        render_icon_composer_layer(args.source, args.foreground)


if __name__ == "__main__":
    main()

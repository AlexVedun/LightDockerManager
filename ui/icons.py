from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QStyle

_LINE_COLOR = "#5a5a5a"
_LINE_WIDTH = 1.5
_CANVAS = 20  # the coordinates below are tuned for a 20x20 canvas
_SIZES = (16, 20, 24, 32, 48, 64)


def standard_icon(name):
    """Returns the native QIcon for a QStyle.StandardPixmap name (e.g. "SP_MediaPlay").

    Uses the platform style's own icon set rather than bundled image files,
    so it needs no extra assets and matches the current theme automatically.
    """
    return QApplication.instance().style().standardIcon(getattr(QStyle.StandardPixmap, name))


def _multi_resolution_icon(draw):
    """Builds a QIcon by rendering `draw(painter)` at several pixel sizes.

    A QIcon backed by a single low-resolution pixmap looks blurry whenever
    Qt displays it larger than that (a bigger toolbar icon size, HiDPI
    scaling, ...) since it has to upscale with interpolation. Rendering at
    several sizes up front and stroking each at its own resolution (via a
    matching painter scale, so line width stays proportional) lets Qt pick
    an exact match instead, so it always renders crisp.
    """
    icon = QIcon()
    for size in _SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(size / _CANVAS, size / _CANVAS)
        draw(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def trash_icon():
    """A small hand-drawn trash-can glyph, flat and monochrome like the rest of the toolbar.

    Some desktop icon themes map QStyle.SP_TrashIcon to a busy, colorful
    bitmap (e.g. a green recycle-bin) that clashes with the app's other
    flat outline icons, so "Remove" gets a simple line-drawn one instead
    that looks the same everywhere.
    """

    def draw(painter):
        pen = QPen(_LINE_COLOR)
        pen.setWidthF(_LINE_WIDTH)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        painter.drawLine(QPointF(4, 6), QPointF(16, 6))
        painter.drawLine(QPointF(8, 6), QPointF(8.5, 3.5))
        painter.drawLine(QPointF(8.5, 3.5), QPointF(11.5, 3.5))
        painter.drawLine(QPointF(11.5, 3.5), QPointF(12, 6))

        body = [QPointF(5.7, 6.5), QPointF(14.3, 6.5), QPointF(13.3, 17), QPointF(6.7, 17)]
        for start, end in zip(body, body[1:] + body[:1]):
            painter.drawLine(start, end)

        painter.drawLine(QPointF(8.4, 9), QPointF(8.6, 14.5))
        painter.drawLine(QPointF(10, 9), QPointF(10, 14.5))
        painter.drawLine(QPointF(11.6, 9), QPointF(11.4, 14.5))

    return _multi_resolution_icon(draw)

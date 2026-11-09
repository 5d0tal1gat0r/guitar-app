"""Visual system: palette, application stylesheet and painted tool icons.

Every colour the shell uses comes from PALETTE so the look stays coherent.
Icons are painted with QPainter on a 24-unit grid with one stroke weight,
so they scale cleanly and need no image assets.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

PALETTE: dict[str, str] = {
    # Approved roles.
    "cream": "#FFF6E7",
    "navy": "#1D2B3D",
    "peach": "#EFA77D",
    "honey": "#E3B652",
    "green": "#B9D0A9",
    "blue": "#91ACD2",
    # Supporting tints derived from the roles above.
    "paper": "#FFFCF6",
    "sand": "#F3E6CF",
    "line": "#E2D2B6",
    "ink_soft": "#4A586B",
    "navy_hover": "#2C3E55",
}

# (text role, surface role) pairs that the stylesheet actually combines.
TEXT_PAIRS: tuple[tuple[str, str], ...] = (
    ("navy", "cream"),
    ("navy", "paper"),
    ("navy", "sand"),
    ("ink_soft", "cream"),
    ("ink_soft", "paper"),
    ("navy", "peach"),
    ("navy", "honey"),
    ("navy", "green"),
    ("navy", "blue"),
    ("cream", "navy"),
    ("cream", "navy_hover"),
)


def application_stylesheet() -> str:
    p = PALETTE
    return f"""
QMainWindow, QDialog {{
    background: {p["cream"]};
}}
QWidget {{
    color: {p["navy"]};
    font-size: 10.5pt;
}}
QWidget#Shell, QStackedWidget#Pages {{
    background: {p["cream"]};
}}

/* Typography hierarchy */
QLabel#PageTitle {{
    font-size: 24pt;
    font-weight: 800;
    color: {p["navy"]};
}}
QLabel#Eyebrow {{
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 1px;
    color: {p["ink_soft"]};
}}
QLabel#Muted {{
    color: {p["ink_soft"]};
}}
QLabel#Metric {{
    font-size: 20pt;
    font-weight: 800;
}}

/* Navigation rail */
QWidget#NavRail {{
    background: {p["navy"]};
}}
QLabel#Brand {{
    color: {p["cream"]};
    font-size: 13pt;
    font-weight: 800;
    padding: 4px 6px 14px 6px;
}}
QPushButton#NavButton {{
    background: transparent;
    color: {p["cream"]};
    border: 2px solid transparent;
    border-radius: 10px;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
}}
QPushButton#NavButton:hover {{
    background: {p["navy_hover"]};
}}
QPushButton#NavButton:checked {{
    background: {p["cream"]};
    color: {p["navy"]};
}}
QPushButton#NavButton:focus {{
    border-color: {p["honey"]};
}}

/* Home action cards */
QPushButton#ActionCard {{
    background: {p["paper"]};
    color: {p["navy"]};
    border: 2px solid {p["line"]};
    border-radius: 16px;
    padding: 14px;
    text-align: left;
}}
QPushButton#ActionCard:hover {{
    border-color: {p["navy"]};
}}
QPushButton#ActionCard:pressed {{
    background: {p["sand"]};
}}
QPushButton#ActionCard:focus {{
    border: 3px solid {p["navy"]};
}}
QWidget#SummaryPanel {{
    background: {p["sand"]};
    border-radius: 16px;
}}

/* Toolbar */
QToolBar {{
    background: {p["paper"]};
    border: none;
    border-bottom: 1px solid {p["line"]};
    padding: 6px 10px;
    spacing: 8px;
}}

/* Controls */
QPushButton {{
    background: {p["paper"]};
    color: {p["navy"]};
    border: 1px solid {p["line"]};
    border-radius: 8px;
    padding: 6px 12px;
}}
QPushButton:hover {{
    border-color: {p["navy"]};
}}
QPushButton:checked {{
    background: {p["green"]};
    border-color: {p["navy"]};
}}
QPushButton:focus {{
    border: 2px solid {p["navy"]};
}}
QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled {{
    color: {p["ink_soft"]};
    background: {p["sand"]};
    border-color: {p["sand"]};
}}
QComboBox, QSpinBox, QLineEdit, QPlainTextEdit, QListWidget, QTableWidget {{
    background: {p["paper"]};
    color: {p["navy"]};
    border: 1px solid {p["line"]};
    border-radius: 8px;
    padding: 4px 8px;
    selection-background-color: {p["blue"]};
    selection-color: {p["navy"]};
}}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus, QPlainTextEdit:focus,
QListWidget:focus, QTableWidget:focus {{
    border: 2px solid {p["navy"]};
}}
QComboBox QAbstractItemView {{
    background: {p["paper"]};
    selection-background-color: {p["blue"]};
    selection-color: {p["navy"]};
}}
QGroupBox {{
    border: 1px solid {p["line"]};
    border-radius: 12px;
    margin-top: 14px;
    padding: 10px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}}
QTabBar::tab {{
    background: transparent;
    color: {p["ink_soft"]};
    padding: 6px 14px;
    border-bottom: 3px solid transparent;
}}
QTabBar::tab:selected {{
    color: {p["navy"]};
    border-bottom-color: {p["peach"]};
    font-weight: 700;
}}
QTabBar::tab:hover {{
    color: {p["navy"]};
}}
QTabWidget::pane {{
    border: none;
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: {p["line"]};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {p["navy"]};
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:focus {{
    background: {p["navy_hover"]};
    border: 2px solid {p["honey"]};
}}
QStatusBar {{
    background: {p["paper"]};
    color: {p["ink_soft"]};
    border-top: 1px solid {p["line"]};
}}
"""


# ----------------------------------------------------------------- Icons

def _home(p: QPainter) -> None:
    p.drawPolyline(QPolygonF([QPointF(3, 11), QPointF(12, 3.5), QPointF(21, 11)]))
    p.drawRoundedRect(QRectF(5.5, 10, 13, 10.5), 1.5, 1.5)
    p.drawLine(QPointF(10, 20.5), QPointF(10, 15))
    p.drawLine(QPointF(10, 15), QPointF(14, 15))
    p.drawLine(QPointF(14, 15), QPointF(14, 20.5))


def _library(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(3, 5, 4, 15.5), 1, 1)
    p.drawRoundedRect(QRectF(8.5, 3, 4, 17.5), 1, 1)
    p.save()
    p.translate(15, 20.5)
    p.rotate(-16)
    p.drawRoundedRect(QRectF(0, -16, 4, 16), 1, 1)
    p.restore()
    p.drawLine(QPointF(2, 21), QPointF(22, 21))


def _practice(p: QPainter) -> None:
    # Plectrum with a play mark.
    path = QPainterPath(QPointF(12, 21))
    path.cubicTo(QPointF(6, 15), QPointF(3, 10), QPointF(4, 6.5))
    path.cubicTo(QPointF(5, 3), QPointF(19, 3), QPointF(20, 6.5))
    path.cubicTo(QPointF(21, 10), QPointF(18, 15), QPointF(12, 21))
    p.drawPath(path)
    p.drawPolygon(QPolygonF([QPointF(10, 7.5), QPointF(15, 10.5), QPointF(10, 13.5)]))


def _tuner(p: QPainter) -> None:
    p.drawArc(QRectF(3, 6, 18, 18), 20 * 16, 140 * 16)
    for x1, y1, x2, y2 in ((12, 6, 12, 8.5), (5.2, 9.5, 6.8, 10.8), (18.8, 9.5, 17.2, 10.8)):
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    p.drawLine(QPointF(12, 18), QPointF(15.5, 9.5))
    p.drawEllipse(QPointF(12, 18), 1.6, 1.6)


def _metronome(p: QPainter) -> None:
    p.drawPolygon(QPolygonF([QPointF(9, 3), QPointF(15, 3), QPointF(19.5, 21), QPointF(4.5, 21)]))
    p.drawLine(QPointF(6, 16), QPointF(18, 16))
    p.drawLine(QPointF(12, 16), QPointF(16.5, 6))


def _theory(p: QPainter) -> None:
    for y in (7, 10, 13, 16):
        p.drawLine(QPointF(3, y), QPointF(21, y))
    p.save()
    p.translate(10, 14.5)
    p.rotate(-20)
    p.drawEllipse(QRectF(-2.6, -1.8, 5.2, 3.6))
    p.restore()
    p.drawLine(QPointF(12.3, 13.6), QPointF(12.3, 3.5))
    p.drawLine(QPointF(12.3, 3.5), QPointF(16, 5.5))


def _quiz(p: QPainter) -> None:
    # A fretboard segment with one target dot.
    p.drawRoundedRect(QRectF(3, 6, 18, 12), 1.5, 1.5)
    for x in (9, 15):
        p.drawLine(QPointF(x, 6), QPointF(x, 18))
    for y in (10, 14):
        p.drawLine(QPointF(3, y), QPointF(21, y))
    brush = p.brush()
    p.setBrush(p.pen().color())
    p.drawEllipse(QPointF(12, 12), 2, 2)
    p.setBrush(brush)


def _progress(p: QPainter) -> None:
    p.drawLine(QPointF(3, 21), QPointF(21, 21))
    p.drawRoundedRect(QRectF(4.5, 14, 4, 7), 1, 1)
    p.drawRoundedRect(QRectF(10, 10, 4, 11), 1, 1)
    p.drawRoundedRect(QRectF(15.5, 4.5, 4, 16.5), 1, 1)


TOOL_ICONS: dict[str, Callable[[QPainter], None]] = {
    "home": _home,
    "library": _library,
    "practice": _practice,
    "tuner": _tuner,
    "metronome": _metronome,
    "theory": _theory,
    "quiz": _quiz,
    "progress": _progress,
}


def tool_pixmap(name: str, size: int = 48, color: str | None = None) -> QPixmap:
    draw = TOOL_ICONS[name]
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = size / 24
    painter.scale(scale, scale)
    pen = QPen(QColor(color or PALETTE["navy"]))
    # 2 px on screen at any size, never thinner than the 24-unit grid allows.
    pen.setWidthF(max(2.0, size / 16) / scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    draw(painter)
    painter.end()
    return pixmap


def tool_icon(name: str, size: int = 48, color: str | None = None) -> QIcon:
    return QIcon(tool_pixmap(name, size, color))

"""Custom-painted widgets: cents meter, fretboard, step strip, level meter."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .practice import Verdict
from .theory import STANDARD_TUNING, STRING_NAMES

GREEN = QColor("#3fb950")
AMBER = QColor("#d29922")
RED = QColor("#f85149")
GREY = QColor("#6e7681")
BLUE = QColor("#58a6ff")

VERDICT_COLORS = {
    Verdict.CORRECT: GREEN,
    Verdict.OUT_OF_TUNE: AMBER,
    Verdict.WRONG: RED,
    Verdict.MISSED: GREY,
}


def _muted(widget: QWidget, alpha: int = 90) -> QColor:
    color = QColor(widget.palette().text().color())
    color.setAlpha(alpha)
    return color


class CentsMeter(QWidget):
    """Horizontal -50..+50 cent scale with a needle. Green when within `in_tune` cents."""

    def __init__(self, in_tune: float = 5.0, parent=None):
        super().__init__(parent)
        self.in_tune = in_tune
        self.cents: float | None = None
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_cents(self, cents: float | None) -> None:
        self.cents = cents
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        margin = 16
        span = w - 2 * margin

        def x_for(c: float) -> float:
            return margin + (max(-50.0, min(50.0, c)) + 50.0) / 100.0 * span

        zone = QColor(GREEN)
        zone.setAlpha(50)
        p.fillRect(QRectF(x_for(-self.in_tune), 8, x_for(self.in_tune) - x_for(-self.in_tune), h - 26), zone)
        p.setPen(QPen(_muted(self), 1))
        for c in range(-50, 51, 10):
            tick = 14 if c % 50 == 0 else 8
            p.drawLine(QPointF(x_for(c), 8), QPointF(x_for(c), 8 + tick))
        p.setFont(QFont(self.font().family(), 8))
        for c, label in ((-50, "-50"), (0, "0"), (50, "+50")):
            p.drawText(QRectF(x_for(c) - 20, h - 16, 40, 14), Qt.AlignmentFlag.AlignCenter, label)
        if self.cents is None:
            return
        color = GREEN if abs(self.cents) <= self.in_tune else (AMBER if abs(self.cents) <= 20 else RED)
        pen = QPen(color, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        x = x_for(self.cents)
        p.drawLine(QPointF(x, 4), QPointF(x, h - 20))


class LevelMeter(QWidget):
    """Thin input-level bar so the user can see the mic is picking something up."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.setFixedSize(QSize(90, 10))
        self.setToolTip("Microphone level")

    def set_level(self, rms: float) -> None:
        # Map RMS to a rough 0-1 scale on a log axis (-60 dBFS .. 0 dBFS).
        import math

        db = 20 * math.log10(max(rms, 1e-6))
        self.level = max(0.0, min(1.0, (db + 60) / 60))
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), _muted(self, 40))
        p.fillRect(QRectF(0, 0, self.width() * self.level, self.height()), GREEN if self.level < 0.9 else RED)


@dataclass(frozen=True)
class FretMark:
    string: int  # 0 = lowest string
    fret: int
    label: str
    color: QColor
    filled: bool = True


class Fretboard(QWidget):
    """Guitar neck seen from the player: high e on top, nut on the left."""

    INLAYS = (3, 5, 7, 9, 15, 17, 19, 21)

    def __init__(self, frets: int = 15, tuning: tuple[int, ...] = STANDARD_TUNING, parent=None):
        super().__init__(parent)
        self.frets = frets
        self.tuning = tuning
        self.marks: list[FretMark] = []
        self.setMinimumSize(560, 130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_marks(self, marks: list[FretMark]) -> None:
        self.marks = marks
        self.update()

    def _geometry(self) -> tuple[float, float, float, float]:
        left, top, bottom_margin = 36.0, 16.0, 40.0  # room for fret numbers below the low string
        fret_w = (self.width() - left - 10) / (self.frets + 1)
        string_gap = (self.height() - top - bottom_margin) / (len(self.tuning) - 1)
        return left, top, fret_w, string_gap

    def _string_y(self, string: int) -> float:
        _, top, _, gap = self._geometry()
        return top + (len(self.tuning) - 1 - string) * gap

    def _fret_x(self, fret: int) -> float:
        """Centre of the space where a finger presses `fret` (fret 0 sits left of the nut)."""
        left, _, fret_w, _ = self._geometry()
        return left + (fret + 0.5) * fret_w

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, top, fret_w, gap = self._geometry()
        bottom = top + gap * (len(self.tuning) - 1)
        line = _muted(self, 110)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_muted(self, 35))
        for fret in self.INLAYS:
            if fret <= self.frets:
                p.drawEllipse(QPointF(self._fret_x(fret), (top + bottom) / 2), 5, 5)
        if self.frets >= 12:
            for y in (top + gap * 1.5, bottom - gap * 1.5):
                p.drawEllipse(QPointF(self._fret_x(12), y), 5, 5)

        for fret in range(1, self.frets + 2):
            x = left + fret * fret_w
            p.setPen(QPen(line, 4 if fret == 1 else 1))
            p.drawLine(QPointF(x, top), QPointF(x, bottom))

        p.setFont(QFont(self.font().family(), 8))
        for string in range(len(self.tuning)):
            y = self._string_y(string)
            p.setPen(QPen(line, 2 if string < 3 else 1))  # wound strings thicker
            p.drawLine(QPointF(left + fret_w, y), QPointF(left + (self.frets + 1) * fret_w, y))
            p.setPen(self.palette().text().color())
            name = STRING_NAMES[string] if self.tuning == STANDARD_TUNING else ""
            p.drawText(QRectF(0, y - 8, left - 22, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name)

        p.setPen(_muted(self, 160))
        for fret in range(0, self.frets + 1, 1):
            if fret in (0, 3, 5, 7, 9, 12, 15, 17, 19, 21):
                p.drawText(QRectF(self._fret_x(fret) - 12, bottom + 18, 24, 14), Qt.AlignmentFlag.AlignCenter, str(fret))

        radius = max(8.0, min(13.0, gap * 0.45, fret_w * 0.38))
        font = QFont(self.font().family(), 8)
        font.setBold(True)
        p.setFont(font)
        for mark in self.marks:
            if mark.fret > self.frets:
                continue
            centre = QPointF(self._fret_x(mark.fret), self._string_y(mark.string))
            if mark.filled:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(mark.color)
            else:
                p.setPen(QPen(mark.color, 3))
                p.setBrush(self.palette().window().color())
            p.drawEllipse(centre, radius, radius)
            p.setPen(QColor("white") if mark.filled else self.palette().text().color())
            p.drawText(QRectF(centre.x() - radius, centre.y() - radius, 2 * radius, 2 * radius),
                       Qt.AlignmentFlag.AlignCenter, mark.label)


class StepStrip(QWidget):
    """One cell per exercise step, coloured by verdict; the current step is outlined."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels: list[str] = []
        self.verdicts: dict[int, Verdict] = {}
        self.current: int | None = None
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_steps(self, labels: list[str]) -> None:
        self.labels = labels
        self.verdicts = {}
        self.current = None
        self.update()

    def set_verdict(self, index: int, verdict: Verdict) -> None:
        self.verdicts[index] = verdict
        self.update()

    def set_current(self, index: int | None) -> None:
        self.current = index
        self.update()

    def paintEvent(self, _event) -> None:
        if not self.labels:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cell = 46.0
        visible = max(1, int(self.width() // cell))
        # Keep the current step in view: scroll in pages.
        first = 0
        if self.current is not None:
            first = (self.current // visible) * visible
        p.setFont(QFont(self.font().family(), 8))
        for slot, index in enumerate(range(first, min(len(self.labels), first + visible))):
            rect = QRectF(slot * cell + 2, 4, cell - 4, self.height() - 8)
            verdict = self.verdicts.get(index)
            if verdict is not None:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(VERDICT_COLORS[verdict])
            else:
                p.setPen(QPen(_muted(self, 70), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 5, 5)
            if index == self.current:
                p.setPen(QPen(BLUE, 3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 6, 6)
            p.setPen(QColor("white") if verdict is not None else self.palette().text().color())
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.labels[index])

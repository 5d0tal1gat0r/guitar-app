"""Custom-painted widgets: cents meter, fretboard, scrolling tab view, level meter."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .practice import Verdict
from .tabs import Exercise
from .theme import PALETTE
from .theory import STANDARD_TUNING, STRING_NAMES

# Deep tones of the theme accents: white text on them meets 4.5:1.
GREEN = QColor(PALETTE["correct"])
AMBER = QColor(PALETTE["tune"])
RED = QColor(PALETTE["wrong"])
GREY = QColor(PALETTE["missed"])
BLUE = QColor(PALETTE["target"])

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


class TabView(QWidget):
    """The exercise as tablature that scrolls with play.

    One column per step, high e on top. Played steps are coloured by verdict,
    the current step sits in a highlighted band in the left third so the
    upcoming notes stay visible, and the loop range is shaded.
    Clicking a column emits `step_clicked(index, shift_held)`.
    """

    COLUMN = 34.0
    LEFT = 26.0
    step_clicked = Signal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.exercise: Exercise | None = None
        self.verdicts: dict[int, Verdict] = {}
        self.current: int | None = None
        self.loop_range: tuple[int, int] | None = None
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click a step to start the loop there; Shift+click to end it")

    def sizeHint(self) -> QSize:
        return QSize(600, 150)

    def set_exercise(self, exercise: Exercise | None) -> None:
        self.exercise = exercise
        self.loop_range = None
        self.reset()

    def reset(self) -> None:
        self.verdicts = {}
        self.current = None
        self.update()

    def set_verdict(self, index: int, verdict: Verdict) -> None:
        self.verdicts[index] = verdict
        self.update()

    def set_current(self, index: int | None) -> None:
        self.current = index
        self.update()

    def set_range(self, first: int | None, last: int | None = None) -> None:
        self.loop_range = None if first is None else (first, last if last is not None else first)
        self.update()

    def _first_visible(self) -> int:
        if self.exercise is None or self.current is None:
            return 0
        visible = max(1, int((self.width() - self.LEFT) // self.COLUMN))
        first = self.current - visible // 3
        return max(0, min(first, len(self.exercise.steps) - visible))

    def column_x(self, index: int) -> float:
        return self.LEFT + (index - self._first_visible()) * self.COLUMN

    def _string_y(self, string: int) -> float:
        top, gap = 16.0, (self.height() - 16.0 - 34.0) / 5
        return top + (5 - string) * gap

    def mousePressEvent(self, event) -> None:
        if self.exercise is None or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        index = self._first_visible() + int((event.position().x() - self.LEFT) // self.COLUMN)
        if 0 <= index < len(self.exercise.steps) and event.position().x() >= self.LEFT:
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.step_clicked.emit(index, shift)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        line = QColor(PALETTE["ink_soft"])
        line.setAlpha(90)
        ink = QColor(PALETTE["navy"])
        soft = QColor(PALETTE["ink_soft"])
        top, bottom = self._string_y(5), self._string_y(0)

        p.setPen(QPen(line, 1))
        for string in range(6):
            y = self._string_y(string)
            p.drawLine(QPointF(self.LEFT - 4, y), QPointF(self.width(), y))
        small = QFont(self.font().family(), 8)
        p.setFont(small)
        p.setPen(soft)
        for string in range(6):
            y = self._string_y(string)
            p.drawText(QRectF(0, y - 8, self.LEFT - 8, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, STRING_NAMES[string])
        exercise = self.exercise
        if exercise is None:
            return

        first = self._first_visible()
        last = min(len(exercise.steps), first + int((self.width() - self.LEFT) // self.COLUMN) + 1)
        if self.loop_range is not None:
            a, b = self.loop_range
            x1 = max(self.LEFT, self.column_x(max(a, first)))
            x2 = self.column_x(min(b, last - 1)) + self.COLUMN
            if a < last and b >= first:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(PALETTE["sand"]))
                p.drawRoundedRect(QRectF(x1, 4, x2 - x1, self.height() - 8), 8, 8)
                p.setPen(QPen(QColor(PALETTE["honey"]), 3))
                if first <= a < last:
                    p.drawLine(QPointF(x1, 6), QPointF(x1, self.height() - 6))
                if first <= b < last:
                    p.drawLine(QPointF(x2, 6), QPointF(x2, self.height() - 6))
        if self.current is not None and first <= self.current < last:
            x = self.column_x(self.current)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(PALETTE["blue"]))
            p.drawRoundedRect(QRectF(x + 2, top - 14, self.COLUMN - 4, bottom - top + 28), 8, 8)

        bold = QFont(self.font().family(), 10)
        bold.setBold(True)
        for index in range(first, last):
            step = exercise.steps[index]
            x = self.column_x(index)
            verdict = self.verdicts.get(index)
            for string, fret in step.notes:
                y = self._string_y(string)
                cell = QRectF(x + 5, y - 10, self.COLUMN - 10, 20)
                if verdict is not None:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(VERDICT_COLORS[verdict])
                    p.drawRoundedRect(cell, 6, 6)
                    p.setPen(QColor("white"))
                else:
                    # Knock the string line out behind the number.
                    p.setPen(Qt.PenStyle.NoPen)
                    in_loop = self.loop_range is not None and self.loop_range[0] <= index <= self.loop_range[1]
                    backdrop = "blue" if index == self.current else "sand" if in_loop else "cream"
                    p.setBrush(QColor(PALETTE[backdrop]))
                    p.drawRect(cell.adjusted(3, 2, -3, -2))
                    p.setPen(ink)
                p.setFont(bold)
                p.drawText(cell, Qt.AlignmentFlag.AlignCenter, str(fret))
            p.setFont(small)
            p.setPen(ink if index == self.current else soft)
            p.drawText(QRectF(x, bottom + 14, self.COLUMN, 16), Qt.AlignmentFlag.AlignCenter, str(index + 1))

"""Home screen: one dominant "practice a song" action, tool shortcuts and a real summary."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .history import History
from .tabs import load_library
from .theme import PALETTE, tool_pixmap

# route, title, description, icon, accent palette role
HOME_ACTIONS: tuple[tuple[str, str, str, str, str], ...] = (
    ("library", "Practice a song",
     "Pick a song or exercise, set the tempo and play along. The app listens and marks every note.",
     "practice", "peach"),
    ("tuner", "Tune up", "Get every string in tune before you start.", "tuner", "blue"),
    ("metronome", "Metronome", "Steady clicks and a speed trainer.", "metronome", "honey"),
    ("theory", "Theory", "Scales, chords and where they sit on the neck.", "theory", "green"),
    ("quiz", "Quiz", "Learn the fretboard and train your ear.", "quiz", "blue"),
    ("progress", "Progress", "Sessions, best accuracy and tempo records.", "progress", "honey"),
)


def icon_tile(icon: str, accent: str, size: int) -> QPixmap:
    """The icon on a rounded tile of its accent colour."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(PALETTE[accent]))
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    inner = int(size * 0.6)
    offset = (size - inner) // 2
    painter.drawPixmap(offset, offset, tool_pixmap(icon, inner))
    painter.end()
    return pixmap


class ElidedLabel(QLabel):
    """Single-line label that elides instead of growing its parent."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self.full_text = text
        self.setToolTip(text)
        self._elide()

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = max(self.width(), 40)
        super().setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideRight, width))


class ActionCard(QPushButton):
    """A whole-card button: icon tile, title and description. Space, Enter and click activate it."""

    def __init__(self, route: str, title: str, description: str, icon_name: str,
                 parent: QWidget | None = None, accent: str = "blue", hero: bool = False):
        super().__init__(parent)
        self.route = route
        self.setObjectName("ActionCard")
        self.setProperty("hero", hero)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.setToolTip(description)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        tile = QLabel()
        tile.setPixmap(icon_tile(icon_name, "paper" if hero else accent, 64 if hero else 40))
        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        self.title_label.setWordWrap(True)
        self.description_label = QLabel(description)
        self.description_label.setObjectName("Muted")
        self.description_label.setWordWrap(True)
        for label in (tile, self.title_label, self.description_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)
        layout.addWidget(tile)
        if hero:
            layout.addStretch(1)
        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        if not hero:
            layout.addStretch(1)

    def sizeHint(self) -> QSize:
        return self.layout().sizeHint()

    def minimumSizeHint(self) -> QSize:
        return self.layout().minimumSize()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.isAutoRepeat():
            self.click()
            return
        super().keyPressEvent(event)


class HomePage(QWidget):
    route_requested = Signal(str)

    def __init__(self, history: History, library_loader: Callable = load_library, parent=None):
        super().__init__(parent)
        self.history = history
        self.library_loader = library_loader

        eyebrow = QLabel("GUITAR PRACTICE")
        eyebrow.setObjectName("Eyebrow")
        title = QLabel("What do you want to play today?")
        title.setObjectName("PageTitle")
        title.setWordWrap(True)
        self.mic_label = QLabel()
        self.mic_label.setObjectName("StatusChip")

        header = QVBoxLayout()
        header.setSpacing(4)
        header.addWidget(eyebrow)
        header.addWidget(title)
        status = QHBoxLayout()
        status.addWidget(self.mic_label)
        status.addStretch(1)
        header.addLayout(status)

        self.cards: list[ActionCard] = []
        for route, card_title, description, icon, accent in HOME_ACTIONS:
            card = ActionCard(route, card_title, description, icon, accent=accent, hero=route == "library")
            card.clicked.connect(lambda _checked=False, r=route: self.route_requested.emit(r))
            self.cards.append(card)

        grid = QGridLayout()
        grid.setSpacing(14)
        hero, tuner, metronome, theory, quiz, progress = self.cards
        grid.addWidget(hero, 0, 0, 3, 1)
        grid.addWidget(tuner, 0, 1)
        grid.addWidget(metronome, 0, 2)
        grid.addWidget(theory, 1, 1)
        grid.addWidget(quiz, 1, 2)
        grid.addWidget(progress, 2, 1)
        grid.addWidget(self._build_summary(), 2, 2)
        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 4)
        grid.setColumnStretch(2, 4)
        for row in range(3):
            grid.setRowStretch(row, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addLayout(header)
        layout.addLayout(grid, 1)

        self.set_microphone_state(False)
        self.refresh()

    def _build_summary(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("SummaryPanel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        caption = QLabel("LAST PRACTICED")
        caption.setObjectName("Eyebrow")
        self.recent_label = ElidedLabel()
        self.recent_label.setObjectName("CardTitle")
        self.streak_label = QLabel()
        self.streak_label.setObjectName("Metric")
        self.library_label = QLabel()
        self.library_label.setObjectName("Muted")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        layout.addWidget(caption)
        layout.addWidget(self.recent_label)
        layout.addStretch(1)
        layout.addWidget(self.streak_label)
        layout.addWidget(self.library_label)
        return panel

    def refresh(self) -> None:
        exercises, _errors = self.library_loader()
        count = len(exercises)
        self.library_label.setText(f"{count} exercise{'' if count == 1 else 's'} in your library")
        self.streak_label.setText(f"{self.history.streak()} day streak")
        records = self.history.records
        if records:
            latest = max(reversed(records), key=lambda record: record.when)
            self.recent_label.set_full_text(latest.title)
        else:
            self.recent_label.set_full_text("No practice yet")

    def set_microphone_state(self, active: bool) -> None:
        self.mic_label.setProperty("active", active)
        self.mic_label.setText("Microphone ready" if active else "Microphone off")
        self.mic_label.setAccessibleName("Microphone ready" if active else "Microphone off")
        self.mic_label.style().unpolish(self.mic_label)
        self.mic_label.style().polish(self.mic_label)

"""Quiz page (fretboard notes, intervals by ear) and Progress page."""

from __future__ import annotations

import random
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from .history import CLEAN_ACCURACY, History
from .pitch import NoteReading
from .quiz import (
    ALL_INTERVALS, BASIC_INTERVALS, IntervalQuestion, NoteQuestion, Score, interval_audio,
    interval_question, is_right_name, is_right_played, note_question,
)
from .theory import NOTE_NAMES, STRING_NAMES, interval_name, midi_name
from .widgets import BLUE, GREEN, GREY, RED, Fretboard, FretMark

SAMPLE_RATE = 44100
NEXT_DELAY_MS = 900


def _big(label: QLabel, size: int) -> QLabel:
    font = label.font()
    font.setPointSize(size)
    font.setBold(True)
    label.setFont(font)
    return label


def _color(label: QLabel, color) -> None:
    label.setStyleSheet(f"color: {color.name()};" if color is not None else "")


class FretboardQuiz(QWidget):
    """Name the marked note by clicking, or find it by playing it."""

    def __init__(self, hub):
        super().__init__()
        self.rng = random.Random()
        self.score = Score()
        self.question: NoteQuestion | None = None
        self.waiting = False

        self.max_fret = QSpinBox()
        self.max_fret.setRange(3, 15)
        self.max_fret.setValue(12)
        self.by_playing = QCheckBox("Answer by playing")
        self.by_playing.setToolTip("Play the marked fret instead of naming it. The exact octave must match.")
        self.by_playing.toggled.connect(self.next_question)
        options = QHBoxLayout()
        options.addWidget(QLabel("Up to fret"))
        options.addWidget(self.max_fret)
        options.addWidget(self.by_playing)
        options.addStretch(1)

        self.prompt = _big(QLabel(), 18)
        self.feedback = _big(QLabel(" "), 14)
        self.score_label = QLabel(str(self.score))
        _color(self.score_label, GREY)
        self.fretboard = Fretboard(frets=15)

        self.buttons = QGridLayout()
        self.note_buttons: list[QPushButton] = []
        for pc, name in enumerate(NOTE_NAMES):
            button = QPushButton(name)
            button.setMinimumHeight(36)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, p=pc: self.answer_name(p))
            self.buttons.addWidget(button, 0, pc)
            self.note_buttons.append(button)

        layout = QVBoxLayout(self)
        layout.addLayout(options)
        layout.addWidget(self.prompt)
        layout.addWidget(self.fretboard, 1)
        layout.addLayout(self.buttons)
        layout.addWidget(self.feedback)
        layout.addWidget(self.score_label)
        hub.note.connect(self.answer_played)
        self.next_question()

    def next_question(self) -> None:
        self.waiting = False
        self.question = note_question(self.rng, self.max_fret.value(), previous=self.question)
        q = self.question
        place = f"{STRING_NAMES[q.string]} string, {'open' if q.fret == 0 else f'fret {q.fret}'}"
        if self.by_playing.isChecked():
            self.prompt.setText(f"Play: {place}")
        else:
            self.prompt.setText("Which note is this?")
        self.fretboard.set_marks([FretMark(q.string, q.fret, "?", BLUE)])
        for button in self.note_buttons:
            button.setEnabled(not self.by_playing.isChecked())
        self.feedback.setText(" ")

    def answer_name(self, pitch_class: int) -> None:
        if self.question is None or self.waiting:
            return
        self._resolve(is_right_name(self.question, pitch_class), NOTE_NAMES[pitch_class])

    def answer_played(self, reading: NoteReading) -> None:
        if not self.isVisible() or not self.by_playing.isChecked() or self.question is None or self.waiting:
            return
        self._resolve(is_right_played(self.question, reading), midi_name(reading.midi))

    def _resolve(self, correct: bool, given: str) -> None:
        q = self.question
        self.waiting = True
        self.score.record(correct)
        self.score_label.setText(str(self.score))
        answer = midi_name(q.midi) if self.by_playing.isChecked() else NOTE_NAMES[q.midi % 12]
        self.fretboard.set_marks([FretMark(q.string, q.fret, NOTE_NAMES[q.midi % 12], GREEN if correct else RED)])
        self.feedback.setText(f"Right: {answer}" if correct else f"{given} — it is {answer}")
        _color(self.feedback, GREEN if correct else RED)
        QTimer.singleShot(NEXT_DELAY_MS if correct else 2 * NEXT_DELAY_MS, self.next_question)


class IntervalQuiz(QWidget):
    """Hear two plucked notes, name the distance between them."""

    def __init__(self):
        super().__init__()
        self.rng = random.Random()
        self.score = Score()
        self.question: IntervalQuestion | None = None
        self.answered = False

        self.level = QComboBox()
        self.level.addItem("Basic: 3rds, 4th, 5th, octave", BASIC_INTERVALS)
        self.level.addItem("All intervals", ALL_INTERVALS)
        self.level.currentIndexChanged.connect(self._level_changed)
        self.harmonic = QCheckBox("Both notes together")
        replay = QPushButton("Play")
        replay.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        replay.clicked.connect(self.play)
        options = QHBoxLayout()
        options.addWidget(self.level)
        options.addWidget(self.harmonic)
        options.addStretch(1)
        options.addWidget(replay)

        intro = QLabel("Tip: link each interval to a song you know. Perfect 4th: the first two notes of "
                       "'Here Comes the Bride'. Perfect 5th: 'Twinkle Twinkle'. Octave: 'Somewhere Over the Rainbow'.")
        intro.setWordWrap(True)
        _color(intro, GREY)
        self.feedback = _big(QLabel("Press Play to hear the first interval"), 14)
        self.score_label = QLabel(str(self.score))
        _color(self.score_label, GREY)

        grid = QGridLayout()
        self.interval_buttons: dict[int, QPushButton] = {}
        for index, semitones in enumerate(ALL_INTERVALS):
            name = "octave" if semitones == 12 else interval_name(semitones)
            button = QPushButton(f"{name}\n{semitones} fret{'s' if semitones > 1 else ''}")
            button.setMinimumHeight(48)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, s=semitones: self.answer(s))
            grid.addWidget(button, index // 4, index % 4)
            self.interval_buttons[semitones] = button

        layout = QVBoxLayout(self)
        layout.addLayout(options)
        layout.addWidget(intro)
        layout.addLayout(grid)
        layout.addWidget(self.feedback)
        layout.addWidget(self.score_label)
        layout.addStretch(1)
        self._level_changed()

    def _level_changed(self) -> None:
        allowed = self.level.currentData()
        for semitones, button in self.interval_buttons.items():
            button.setEnabled(semitones in allowed)
        self.question = None

    def new_question(self) -> None:
        if not self.isVisible():
            return
        self.question = interval_question(self.rng, self.level.currentData())
        self.answered = False
        self.feedback.setText("Listen…")
        _color(self.feedback, None)
        self.play()

    def play(self) -> None:
        if self.question is None:
            self.new_question()
            return
        try:
            import sounddevice as sd

            sd.play(interval_audio(self.question, SAMPLE_RATE, self.harmonic.isChecked()), SAMPLE_RATE)
        except Exception as error:
            self.feedback.setText(f"Audio output failed: {error}")

    def answer(self, semitones: int) -> None:
        if self.question is None:
            self.new_question()
            return
        if self.answered:
            return
        self.answered = True
        q = self.question
        correct = semitones == q.semitones
        self.score.record(correct)
        self.score_label.setText(str(self.score))
        notes = f"{midi_name(q.low)} → {midi_name(q.high)}"
        self.feedback.setText(f"Right: {q.answer} ({notes})" if correct else f"It was a {q.answer} ({notes})")
        _color(self.feedback, GREEN if correct else RED)
        QTimer.singleShot(NEXT_DELAY_MS if correct else 2 * NEXT_DELAY_MS, self.new_question)

    def hideEvent(self, event) -> None:
        self.question = None  # do not keep playing a queued question in the background
        super().hideEvent(event)


class QuizPage(QTabWidget):
    def __init__(self, hub):
        super().__init__()
        self.addTab(FretboardQuiz(hub), "Fretboard notes")
        self.addTab(IntervalQuiz(), "Intervals by ear")


class ProgressPage(QWidget):
    COLUMNS = ("Exercise", "Sessions", "Best accuracy", f"Fastest clean run (≥{CLEAN_ACCURACY:.0%})", "Last played")

    def __init__(self, history: History):
        super().__init__()
        self.history = history
        self.summary = _big(QLabel(), 15)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(self.COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.empty = QLabel("Finish an exercise on the Practice page and your results show up here.")
        _color(self.empty, GREY)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.empty)
        layout.addWidget(self.table, 1)
        self.refresh()

    def showEvent(self, event) -> None:
        self.refresh()
        super().showEvent(event)

    def refresh(self) -> None:
        rows = self.history.all_stats()
        streak = self.history.streak()
        days = "day" if streak == 1 else "days"
        self.summary.setText(f"{len(self.history.records)} sessions · {streak} {days} in a row")
        self.empty.setVisible(not rows)
        self.table.setRowCount(len(rows))
        for row, stats in enumerate(rows):
            last = datetime.fromisoformat(stats.last_played).strftime("%Y-%m-%d %H:%M")
            values = (
                stats.title,
                str(stats.sessions),
                f"{stats.best_accuracy:.0%}",
                f"{stats.best_clean_bpm:.0f} BPM" if stats.best_clean_bpm else "–",
                last,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)

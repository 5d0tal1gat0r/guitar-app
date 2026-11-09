"""Main window: a navigation rail around Home, Practice, Library, Tuner, Metronome, Theory, Quiz and Progress."""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QInputDialog, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSlider, QSpinBox, QSplitter, QTabWidget,
    QStackedWidget, QToolBar, QVBoxLayout, QWidget, QAbstractButton,
)

from . import generator
from .audio import MicInput, input_devices
from .importers import load_import
from .history import History, SessionRecord
from .home import ElidedLabel, HomePage, icon_tile
from .metronome import MAX_BPM, MIN_BPM, Metronome, TapTempo
from .pitch import NoteReading, NoteTracker, Pitch, detect_pitch, reading_from_freq, rms
from .practice import BACK_OFF_BELOW, SPEED_UP_AT, PracticeSession, StepResult, Verdict, next_tempo, section
from .theme import PALETTE, apply_theme, tool_icon
from .tabs import Exercise, TabError, load_library, parse_tab, render_tab, user_dir
from .trainer_ui import ProgressPage, QuizPage
from .theory import (
    CHORDS, NOTE_NAMES, SCALES, STANDARD_TUNING, STRING_NAMES, chord_pitch_classes,
    diatonic_triads, fret_for_midi, fret_positions, interval_name, midi_name, scale_pitch_classes,
)
from .widgets import BLUE, GREEN, GREY, RED, VERDICT_COLORS, CentsMeter, Fretboard, FretMark, LevelMeter, TabView

SAMPLE_RATE = 44100
# Highest note analysed. Guitar fret 19 on high e is B5 (988 Hz).
MAX_FREQ = 1050.0

VERDICT_TEXT = {
    Verdict.CORRECT: "Correct",
    Verdict.OUT_OF_TUNE: "Right note, out of tune",
    Verdict.WRONG: "Wrong note",
    Verdict.MISSED: "Missed",
}

SCALE_NOTES = {
    "major": "The reference scale. Bright and resolved. Every other scale is described against it.",
    "natural minor": "Major with a flat 3rd, 6th and 7th. Darker; the relative minor shares the major's notes.",
    "harmonic minor": "Natural minor with a raised 7th. The 6th-to-7th gap gives its exotic sound.",
    "major pentatonic": "Major without the 4th and 7th. No half steps, so it is hard to hit a bad note.",
    "minor pentatonic": "Minor without the 2nd and 6th. The core of rock and blues soloing.",
    "blues": "Minor pentatonic plus the flat 5th ('blue note'). Use the flat 5th as a passing note.",
    "dorian": "Minor with a natural 6th. Minor but less sad; common in funk, jazz and rock.",
    "mixolydian": "Major with a flat 7th. Sounds like a dominant 7 chord; common in blues and rock.",
    "chromatic": "All twelve notes. Used here for finger and picking technique.",
}

# Pause between runs of a loop, so the player can breathe and see the score.
LOOP_PAUSE_MS = 1500
# Height the live view needs to show the fretboard below the target cards and tab.
FRETBOARD_NEEDS = 400

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII")


def mono_font(size: int = 11) -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(size)
    return font


def big_font(size: int, bold: bool = True) -> QFont:
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    return font


def color_label(label: QLabel, color) -> None:
    label.setStyleSheet(f"color: {color.name()};" if color is not None else "")


def step_pattern(scale: str) -> str:
    """'W W H W W W H' style interval pattern of a scale."""
    steps = SCALES[scale] + (12,)
    names = {1: "H", 2: "W", 3: "W+H"}
    return " ".join(names.get(b - a, str(b - a)) for a, b in zip(steps, steps[1:]))


def position_text(exercise: Exercise, notes: tuple[tuple[int, int], ...]) -> str:
    parts = []
    for string, fret in notes:
        name = STRING_NAMES[string] if exercise.tuning == STANDARD_TUNING else f"string {string + 1}"
        parts.append(f"{name} string, {'open' if fret == 0 else f'fret {fret}'}")
    return " + ".join(parts)


class AudioHub(QObject):
    """Owns the microphone. Analyses the latest audio frame every 20 ms."""

    frame = Signal(object, float)  # Pitch | None, RMS level
    note = Signal(object)  # NoteReading, emitted once per new stable note
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mic = MicInput(SAMPLE_RATE, frame_size=2048)
        self.tracker = NoteTracker(frames_to_confirm=3)
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._analyse)

    @property
    def running(self) -> bool:
        return self.mic.running

    def start(self, device: int | None = None) -> bool:
        self.stop()
        self.mic.device = device
        try:
            self.mic.start()
        except Exception as error:  # PortAudio raises several types
            self.status.emit(f"Microphone unavailable: {error}")
            return False
        self._timer.start()
        self.status.emit("Listening")
        return True

    def stop(self) -> None:
        self._timer.stop()
        self.mic.stop()
        self.tracker.update(None)

    def _analyse(self) -> None:
        samples = self.mic.buffer.latest()
        level = rms(samples)
        pitch = detect_pitch(samples, SAMPLE_RATE, fmax=MAX_FREQ)
        reading = self.tracker.update(pitch, level)
        self.frame.emit(pitch, level)
        if reading is not None:
            self.note.emit(reading)


class BeatBridge(QObject):
    """Carries beat events from the audio thread to the GUI thread."""

    beat = Signal(int)


# --------------------------------------------------------------------- Tuner

class TunerPage(QWidget):
    def __init__(self, hub: AudioHub):
        super().__init__()
        self._smoothed: tuple[int, float] | None = None
        self._last_heard = 0.0

        self.note_label = QLabel("–")
        self.note_label.setFont(big_font(72))
        self.note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label = QLabel("Play a single string")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.meter = CentsMeter()
        self.string_label = QLabel(" ")
        self.string_label.setFont(big_font(13, bold=False))
        self.string_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reference = QLabel("Standard tuning: " + "  ".join(midi_name(m) for m in STANDARD_TUNING))
        reference.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color_label(reference, GREY)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.note_label)
        layout.addWidget(self.detail_label)
        layout.addSpacing(12)
        layout.addWidget(self.meter)
        layout.addWidget(self.string_label)
        layout.addStretch(2)
        layout.addWidget(reference)
        hub.frame.connect(self.on_frame)

    def on_frame(self, pitch: Pitch | None, _level: float) -> None:
        if not self.isVisible():
            return
        now = time.monotonic()
        if pitch is None:
            # Hold the last reading briefly so the display does not flicker between plucks.
            if now - self._last_heard > 1.0:
                self._smoothed = None
                self.meter.set_cents(None)
                color_label(self.note_label, GREY)
            return
        self._last_heard = now
        reading = reading_from_freq(pitch.freq)
        if self._smoothed and self._smoothed[0] == reading.midi:
            cents = 0.7 * self._smoothed[1] + 0.3 * reading.cents
        else:
            cents = reading.cents
        self._smoothed = (reading.midi, cents)

        self.note_label.setText(midi_name(reading.midi))
        in_tune = abs(cents) <= 5
        color_label(self.note_label, GREEN if in_tune else None)
        self.detail_label.setText(f"{pitch.freq:.1f} Hz   {cents:+.0f} cents")
        self.meter.set_cents(cents)

        open_string = min(range(len(STANDARD_TUNING)), key=lambda s: abs(STANDARD_TUNING[s] - reading.midi - cents / 100))
        target = STANDARD_TUNING[open_string]
        offset = (reading.midi - target) * 100 + cents
        if abs(offset) > 250:
            self.string_label.setText(" ")
        elif abs(offset) <= 5:
            self.string_label.setText(f"{STRING_NAMES[open_string]} string ({midi_name(target)}) in tune")
        else:
            direction = "tune up" if offset < 0 else "tune down"
            self.string_label.setText(f"{STRING_NAMES[open_string]} string ({midi_name(target)}): {abs(offset):.0f} cents {'flat' if offset < 0 else 'sharp'}, {direction}")


# ----------------------------------------------------------------- Metronome

class MetronomePage(QWidget):
    def __init__(self, metronome: Metronome, bridge: BeatBridge):
        super().__init__()
        self.metronome = metronome
        self.tap = TapTempo()
        self._bars = 0

        self.bpm_label = QLabel()
        self.bpm_label.setFont(big_font(64))
        self.bpm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bpm_caption = QLabel("BPM")
        bpm_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color_label(bpm_caption, GREY)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(MIN_BPM, MAX_BPM)
        self.slider.valueChanged.connect(self.set_bpm)

        nudges = QHBoxLayout()
        for delta in (-5, -1, +1, +5):
            button = QPushButton(f"{delta:+d}")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, d=delta: self.set_bpm(self.metronome.clock.bpm + d))
            nudges.addWidget(button)
        tap_button = QPushButton("Tap")
        tap_button.setToolTip("Tap at least twice to set the tempo")
        tap_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tap_button.clicked.connect(self.on_tap)
        nudges.addWidget(tap_button)

        self.beats = QSpinBox()
        self.beats.setRange(1, 12)
        self.beats.setValue(4)
        self.beats.valueChanged.connect(self.on_signature)
        self.subdivision = QComboBox()
        for label, value in (("Quarter notes", 1), ("Eighth notes", 2), ("Triplets", 3), ("Sixteenth notes", 4)):
            self.subdivision.addItem(label, value)
        self.subdivision.currentIndexChanged.connect(self.on_signature)
        form = QFormLayout()
        form.addRow("Beats per bar", self.beats)
        form.addRow("Clicks", self.subdivision)

        self.dots = QHBoxLayout()
        self.dots.setSpacing(10)
        self.dots.addStretch(1)
        self.dots.addStretch(1)
        self.dot_labels: list[QLabel] = []

        trainer = QGroupBox("Speed trainer")
        trainer.setCheckable(True)
        trainer.setChecked(False)
        self.trainer = trainer
        self.step_bpm = QSpinBox()
        self.step_bpm.setRange(1, 20)
        self.step_bpm.setValue(5)
        self.every_bars = QSpinBox()
        self.every_bars.setRange(1, 64)
        self.every_bars.setValue(4)
        self.target_bpm = QSpinBox()
        self.target_bpm.setRange(MIN_BPM, MAX_BPM)
        self.target_bpm.setValue(140)
        grid = QHBoxLayout(trainer)
        for widget in (QLabel("Add"), self.step_bpm, QLabel("BPM every"), self.every_bars,
                       QLabel("bars, up to"), self.target_bpm, QLabel("BPM")):
            grid.addWidget(widget)
        grid.addStretch(1)
        trainer_help = QLabel("Start at a tempo you play cleanly. Stop when it gets sloppy; that tempo minus 5 is your next starting point.")
        trainer_help.setWordWrap(True)
        color_label(trainer_help, GREY)

        self.start_button = QPushButton("Start")
        self.start_button.setFont(big_font(13))
        self.start_button.setMinimumHeight(44)
        self.start_button.clicked.connect(self.toggle)
        hint = QLabel("Space starts and stops")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color_label(hint, GREY)

        column = QWidget()
        column.setMaximumWidth(620)
        layout = QVBoxLayout(column)
        layout.addStretch(1)
        layout.addWidget(self.bpm_label)
        layout.addWidget(bpm_caption)
        layout.addLayout(self.dots)
        layout.addSpacing(8)
        layout.addWidget(self.slider)
        layout.addLayout(nudges)
        layout.addLayout(form)
        layout.addWidget(trainer)
        layout.addWidget(trainer_help)
        layout.addStretch(1)
        layout.addWidget(self.start_button)
        layout.addWidget(hint)
        outer = QHBoxLayout(self)
        outer.addWidget(column)

        bridge.beat.connect(self.on_beat)
        self.set_bpm(80)
        self.on_signature()

    def set_bpm(self, bpm: float) -> None:
        bpm = int(round(min(MAX_BPM, max(MIN_BPM, bpm))))
        self.metronome.clock.bpm = bpm
        self.bpm_label.setText(str(bpm))
        if self.slider.value() != bpm:
            self.slider.blockSignals(True)
            self.slider.setValue(bpm)
            self.slider.blockSignals(False)

    def on_tap(self) -> None:
        bpm = self.tap.tap(time.monotonic())
        if bpm is not None:
            self.set_bpm(bpm)

    def on_signature(self) -> None:
        self.metronome.clock.beats_per_bar = self.beats.value()
        self.metronome.clock.subdivision = self.subdivision.currentData()
        while self.dot_labels:
            dot = self.dot_labels.pop()
            self.dots.removeWidget(dot)
            dot.deleteLater()
        for _ in range(self.beats.value()):
            dot = QLabel("●")
            dot.setFont(big_font(20, bold=False))
            color_label(dot, GREY)
            self.dots.insertWidget(self.dots.count() - 1, dot)  # between the two stretches
            self.dot_labels.append(dot)

    def toggle(self) -> None:
        if self.metronome.running:
            self.metronome.stop()
            self.start_button.setText("Start")
            for dot in self.dot_labels:
                color_label(dot, GREY)
            return
        try:
            self.metronome.start()
        except Exception as error:
            QMessageBox.warning(self, "Audio output", f"Could not open the audio output:\n{error}")
            return
        self._bars = 0
        self.start_button.setText("Stop")

    def on_beat(self, beat: int) -> None:
        if not self.metronome.running:
            return
        for index, dot in enumerate(self.dot_labels):
            if index == beat:
                color_label(dot, BLUE if beat == 0 else GREEN)
            else:
                color_label(dot, GREY)
        if beat == 0:
            self._bars += 1
            trainer_due = self._bars > 1 and (self._bars - 1) % self.every_bars.value() == 0
            if self.trainer.isChecked() and trainer_due:
                bpm = self.metronome.clock.bpm
                if bpm < self.target_bpm.value():
                    self.set_bpm(min(self.target_bpm.value(), bpm + self.step_bpm.value()))


# ------------------------------------------------------------------ Practice

class PracticePage(QWidget):
    """Play an exercise against the microphone: live target, scrolling tab, results, loops."""

    library_requested = Signal()

    def __init__(self, hub: AudioHub, metronome: Metronome, history: History):
        super().__init__()
        self.hub = hub
        self.metronome = metronome
        self.history = history
        self.clock = time.monotonic  # replaced in tests
        self.exercise: Exercise | None = None
        self.session: PracticeSession | None = None
        self.offset = 0  # index of the session's first step inside the full exercise
        self.runs = 0  # runs finished in the current loop
        self._started_metronome = False
        self._last_played: tuple[NoteReading, Verdict] | None = None
        self._restart = QTimer(self)
        self._restart.setSingleShot(True)
        self._restart.setInterval(LOOP_PAUSE_MS)
        self._restart.timeout.connect(self._loop_again)

        eyebrow = QLabel("PRACTICE")
        eyebrow.setObjectName("Eyebrow")
        self.title = ElidedLabel("")
        self.title.setObjectName("SectionTitle")
        self.record = QLabel("")
        self.record.setObjectName("Muted")
        self.description = QLabel("")
        self.description.setObjectName("Muted")
        self.description.setWordWrap(True)
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(eyebrow)
        header.addWidget(self.title)
        meta = QHBoxLayout()
        meta.addWidget(self.record)
        meta.addStretch(1)
        header.addLayout(meta)

        self.views = QStackedWidget()
        self.empty_view = self._build_empty()
        self.live_view = self._build_live()
        self.results_view = self._build_results()
        for view in (self.empty_view, self.live_view, self.results_view):
            self.views.addWidget(view)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.views, 1)
        self.controls = self._build_controls()
        layout.addWidget(self.controls)

        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._tick)
        hub.note.connect(self.on_note)
        hub.frame.connect(self.on_frame)
        self.views.setCurrentWidget(self.empty_view)
        self.controls.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # A squashed neck is unreadable; on short windows the tab alone shows where to play.
        self.fretboard.setVisible(self.views.height() >= FRETBOARD_NEEDS)

    # ------------------------------------------------------------ building

    def _build_empty(self) -> QWidget:
        view = QWidget()
        tile = QLabel()
        tile.setPixmap(icon_tile("library", "peach", 72))
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading = QLabel("Pick something to play")
        heading.setObjectName("SectionTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel("Choose a song or exercise in the Library, or generate one. It opens here.")
        body.setObjectName("Muted")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button = QPushButton("Open Library")
        button.setObjectName("Primary")
        button.clicked.connect(self.library_requested.emit)
        column = QVBoxLayout(view)
        column.addStretch(1)
        column.addWidget(tile)
        column.addWidget(heading)
        column.addWidget(body)
        column.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)
        return view

    def _build_live(self) -> QWidget:
        view = QWidget()
        target_card = QWidget()
        target_card.setObjectName("Card")
        target_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        play = QLabel("PLAY")
        play.setObjectName("Eyebrow")
        self.target = QLabel("–")
        self.target.setFont(big_font(34))
        self.position = QLabel(" ")
        self.position.setObjectName("Muted")
        self.feedback = QLabel("Ready")
        self.feedback.setObjectName("Chip")
        target_box = QGridLayout(target_card)
        target_box.setContentsMargins(14, 8, 14, 10)
        target_box.setVerticalSpacing(0)
        target_box.addWidget(play, 0, 0)
        target_box.addWidget(self.target, 1, 0)
        target_box.addWidget(self.position, 2, 0)
        target_box.addWidget(self.feedback, 1, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        target_box.setColumnStretch(0, 1)

        side_card = QWidget()
        side_card.setObjectName("SummaryPanel")
        side_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        hearing = QLabel("HEARING")
        hearing.setObjectName("Eyebrow")
        self.heard = QLabel("–")
        self.heard.setFont(big_font(22))
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.score = QLabel(" ")
        self.score.setObjectName("Muted")
        side = QVBoxLayout(side_card)
        side.setContentsMargins(14, 8, 14, 10)
        side.setSpacing(2)
        side.addWidget(hearing)
        side.addWidget(self.heard)
        side.addStretch(1)
        side.addWidget(self.progress)
        side.addWidget(self.score)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(target_card, 3)
        top.addWidget(side_card, 2)

        self.tab = TabView()
        self.tab.step_clicked.connect(self._on_step_clicked)
        self.fretboard = Fretboard(frets=15)

        column = QVBoxLayout(view)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addLayout(top)
        column.addWidget(self.tab)
        column.addWidget(self.fretboard, 1)
        return view

    def _build_results(self) -> QWidget:
        view = QWidget()
        card = QWidget()
        card.setObjectName("Card")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        done = QLabel("RUN COMPLETE")
        done.setObjectName("Eyebrow")
        self.result_score = QLabel("–")
        self.result_score.setObjectName("Score")
        self.result_caption = QLabel(" ")
        self.result_caption.setObjectName("SectionTitle")
        self.result_caption.setWordWrap(True)
        self.result_chips: dict[Verdict, QLabel] = {}
        chips = QHBoxLayout()
        for verdict in Verdict:
            chip = QLabel()
            chip.setObjectName("Chip")
            chip.setProperty("verdict", verdict.value)
            self.result_chips[verdict] = chip
            chips.addWidget(chip)
        chips.addStretch(1)
        self.result_detail = QLabel(" ")
        self.result_detail.setObjectName("Muted")
        self.result_detail.setWordWrap(True)
        self.result_tab = TabView()
        self.result_tab.setToolTip("Every step of the run, coloured by result")
        self.result_tab.step_clicked.connect(self._on_step_clicked)
        self.again_button = QPushButton("Play again")
        self.again_button.clicked.connect(self.start)
        self.suggested_button = QPushButton("Again at – BPM")
        self.suggested_button.setObjectName("Primary")
        self.suggested_button.clicked.connect(self._start_suggested)
        self.suggested_bpm: int | None = None
        library = QPushButton("Choose another")
        library.clicked.connect(self.library_requested.emit)
        buttons = QHBoxLayout()
        buttons.addWidget(self.suggested_button)
        buttons.addWidget(self.again_button)
        buttons.addStretch(1)
        buttons.addWidget(library)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(22, 16, 22, 18)
        inner.setSpacing(6)
        inner.addWidget(done)
        score_row = QHBoxLayout()
        score_row.addWidget(self.result_score)
        score_row.addWidget(self.result_caption, 1)
        inner.addLayout(score_row)
        inner.addLayout(chips)
        inner.addWidget(self.result_detail)
        inner.addSpacing(6)
        inner.addWidget(self.result_tab)
        inner.addStretch(1)
        inner.addLayout(buttons)
        column = QVBoxLayout(view)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(card)
        return view

    def _build_controls(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("SummaryPanel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.bpm = QSpinBox()
        self.bpm.setRange(MIN_BPM, MAX_BPM)
        self.bpm.setSuffix(" BPM")
        self.tolerance = QSpinBox()
        self.tolerance.setRange(5, 50)
        self.tolerance.setValue(30)
        self.tolerance.setSuffix(" cents")
        self.tolerance.setToolTip("How far off pitch a note may be and still count as correct")
        self.ignore_octave = QCheckBox("Any octave")
        self.ignore_octave.setToolTip("Accept the right note name in any octave")
        self.click = QCheckBox("Click")
        self.click.setChecked(True)
        self.click.setToolTip("Play the metronome during the exercise (one bar count-in)")

        self.first_step = QSpinBox()
        self.last_step = QSpinBox()
        for box in (self.first_step, self.last_step):
            box.setRange(1, 1)
            box.valueChanged.connect(self._on_range_changed)
        self.first_step.setToolTip("First step of the section to play (or click the tab)")
        self.last_step.setToolTip("Last step of the section to play (or Shift+click the tab)")
        self.loop = QCheckBox("Loop")
        self.loop.setToolTip("Repeat the section until you press Stop")
        self.adapt = QCheckBox("Adapt")
        self.adapt.setToolTip(
            f"Each run: {SPEED_UP_AT:.0%}+ correct speeds up, under {BACK_OFF_BELOW:.0%} slows down")
        self.tempo_step = QSpinBox()
        self.tempo_step.setRange(1, 20)
        self.tempo_step.setValue(5)
        self.tempo_step.setPrefix("±")
        self.tempo_step.setToolTip("How much the tempo changes between runs")
        self.goal = QSpinBox()
        self.goal.setRange(MIN_BPM, MAX_BPM)
        self.goal.setValue(MAX_BPM)
        self.goal.setPrefix("max ")
        self.goal.setToolTip("Stop speeding up at this tempo")

        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("Primary")
        self.start_button.setFont(big_font(13))
        self.start_button.setMinimumSize(96, 40)
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.toggle)

        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        def row(*groups):
            line = QHBoxLayout()
            line.setSpacing(4)
            for number, group in enumerate(groups):
                if number:
                    line.addSpacing(12)
                for widget in group:
                    line.addWidget(widget)
            line.addStretch(1)
            return line

        row1 = row((QLabel("Tempo"), self.bpm), (QLabel("Tolerance"), self.tolerance),
                   (self.ignore_octave,), (self.click,))
        row2 = row((QLabel("Steps"), self.first_step, QLabel("to"), self.last_step), (self.loop,),
                   (self.adapt, self.tempo_step, self.goal))
        grid.addLayout(row1, 0, 0)
        grid.addLayout(row2, 1, 0)
        grid.addWidget(self.start_button, 0, 1, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        grid.setColumnStretch(0, 1)
        self.adapt.toggled.connect(self._update_adapt_fields)
        self._update_adapt_fields()
        return panel

    # ------------------------------------------------------------ state

    def load(self, exercise: Exercise) -> None:
        self.stop()
        self.exercise = exercise
        self.title.set_full_text(exercise.title)
        self.description.setText(exercise.description)
        self._show_record()
        self.bpm.setValue(exercise.bpm)
        count = len(exercise.steps)
        for box in (self.first_step, self.last_step):
            box.blockSignals(True)
            box.setRange(1, count)
            box.blockSignals(False)
        self.first_step.setValue(1)
        self.last_step.setValue(count)
        self.tab.set_exercise(exercise)
        self.start_button.setEnabled(True)
        self.controls.show()
        self.views.setCurrentWidget(self.live_view)
        self._set_feedback("Ready", None)
        self.position.setText(f"{count} notes · a one-bar count-in comes first")
        self.score.setText(" ")
        self.progress.setValue(0)
        self._show_step(0)

    def selected_range(self) -> tuple[int, int]:
        """The 0-based inclusive step range the next run plays."""
        return self.first_step.value() - 1, self.last_step.value() - 1

    def _on_range_changed(self, _value: int) -> None:
        if self.exercise is None:
            return
        first, last = self.selected_range()
        if last < first:
            other = self.last_step if self.sender() is self.first_step else self.first_step
            other.blockSignals(True)
            other.setValue(self.first_step.value() if other is self.last_step else self.last_step.value())
            other.blockSignals(False)
            first, last = self.selected_range()
        full = (first, last) == (0, len(self.exercise.steps) - 1)
        self.tab.set_range(None if full else first, last)
        if self.session is None:
            self._show_step(first)

    def _on_step_clicked(self, index: int, shift: bool) -> None:
        if self.session is not None:
            return
        if shift:
            self.last_step.setValue(index + 1)
        else:
            self.first_step.setValue(index + 1)
            if self.last_step.value() < index + 1:
                self.last_step.setValue(index + 1)

    def _update_adapt_fields(self) -> None:
        for widget in (self.tempo_step, self.goal):
            widget.setEnabled(self.adapt.isChecked())

    def _show_record(self) -> None:
        stats = self.history.stats(self.exercise.title) if self.exercise else None
        if stats is None:
            self.record.setText("Not played yet")
            return
        clean = f" · fastest clean run {stats.best_clean_bpm:.0f} BPM" if stats.best_clean_bpm else ""
        self.record.setText(f"Played {stats.sessions}× · best {stats.best_accuracy:.0%}{clean}")

    def _set_feedback(self, text: str, verdict: Verdict | None) -> None:
        self.feedback.setText(text)
        self.feedback.setProperty("verdict", verdict.value if verdict else "")
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

    # ------------------------------------------------------------ running

    def toggle(self) -> None:
        if self.session is None and not self._restart.isActive():
            self.start()
        else:
            looping = self.runs > 0
            self.stop()
            if looping and self.views.currentWidget() is self.live_view:
                self._set_feedback(f"Stopped after {self.runs} run{'s' if self.runs != 1 else ''}", None)
            else:
                self._set_feedback("Stopped", None)

    def _start_suggested(self) -> None:
        if self.suggested_bpm is not None:
            self.bpm.setValue(self.suggested_bpm)
        self.start()

    def start(self) -> None:
        if self.exercise is None:
            return
        if not self.hub.running and not self.hub.start():
            QMessageBox.warning(self, "Microphone", "The microphone could not be opened. Check the input device in the toolbar.")
            return
        first, last = self.selected_range()
        exercise = section(self.exercise, first, last)
        self.offset = first
        bpm = self.bpm.value()
        beats_per_bar = 4
        origin = self.clock()
        if self.click.isChecked():
            if self.metronome.running:
                self.metronome.stop()
            clock = self.metronome.clock
            clock.bpm, clock.beats_per_bar, clock.subdivision = bpm, beats_per_bar, 1
            try:
                self.metronome.start()
                self._started_metronome = True
                origin = self.clock() + self.metronome.output_latency()
            except Exception as error:
                self.position.setText(f"No click: audio output failed ({error}).")
        self.session = PracticeSession(
            exercise,
            start_time=origin + beats_per_bar * 60.0 / bpm,
            bpm=bpm,
            tolerance_cents=self.tolerance.value(),
            ignore_octave=self.ignore_octave.isChecked(),
        )
        self.tab.reset()
        self.tab.set_range(*((first, last) if exercise is not self.exercise else (None,)))
        self.progress.setRange(0, len(exercise.steps))
        self.progress.setValue(0)
        self.score.setText(f"Run {self.runs + 1} · {bpm} BPM" if self.loop.isChecked() else f"{bpm} BPM")
        self._last_played = None
        self._set_feedback("Count-in", None)
        self.views.setCurrentWidget(self.live_view)
        self.start_button.setText("Stop")
        for widget in (self.bpm, self.first_step, self.last_step):
            widget.setEnabled(False)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._restart.stop()
        self.session = None
        self.runs = 0
        if self._started_metronome:
            self.metronome.stop()
            self._started_metronome = False
        self.start_button.setText("Start")
        for widget in (self.bpm, self.first_step, self.last_step):
            widget.setEnabled(True)

    def on_frame(self, pitch: Pitch | None, _level: float) -> None:
        if self.isVisible():
            self.heard.setText(midi_name(reading_from_freq(pitch.freq).midi) if pitch else "–")

    def on_note(self, reading: NoteReading) -> None:
        if self.session is None:
            return
        result = self.session.on_note(self.clock(), reading)
        if result is not None:
            self._show_result(result)

    def _tick(self) -> None:
        session = self.session
        if session is None:
            return
        now = self.clock()
        for result in session.advance(now):
            if result.verdict is Verdict.MISSED:
                self._show_result(result)
            self._update_score(session)
        if session.finished:
            self._finish()
            return
        index = len(session.results)
        if now >= session.step_start(0) - session.early:
            self._show_step(self.offset + index)
            if self.feedback.text() == "Count-in":
                self._set_feedback("Play", None)
        else:
            beats_left = int((session.step_start(0) - now) / session.seconds_per_beat) + 1
            self.target.setText(str(beats_left))
            self.position.setText("Count-in · get ready")

    def _update_score(self, session: PracticeSession) -> None:
        done = len(session.results)
        correct = sum(1 for r in session.results if r.verdict is Verdict.CORRECT)
        self.progress.setValue(done)
        run = f"Run {self.runs + 1} · " if self.loop.isChecked() else ""
        self.score.setText(f"{run}{correct}/{done} correct · {session.bpm:.0f} BPM")

    def _show_step(self, index: int) -> None:
        exercise = self.exercise
        if exercise is None or index >= len(exercise.steps):
            return
        step = exercise.steps[index]
        self.target.setText(" + ".join(midi_name(m) for m in exercise.midi_notes(step)))
        self.position.setText(position_text(exercise, step.notes))
        self.tab.set_current(index)
        marks = []
        if index + 1 < len(exercise.steps):
            for string, fret in exercise.steps[index + 1].notes:
                marks.append(FretMark(string, fret, "", GREY, filled=False))
        if self._last_played is not None:
            reading, verdict = self._last_played
            if verdict is not Verdict.CORRECT:
                places = fret_for_midi(reading.midi, exercise.tuning, max_fret=15)
                if places:
                    near = min(places, key=lambda p: abs(p.fret - step.notes[0][1]) + abs(p.string - step.notes[0][0]))
                    marks.append(FretMark(near.string, near.fret, NOTE_NAMES[reading.midi % 12], VERDICT_COLORS[verdict]))
        for string, fret in step.notes:
            marks.append(FretMark(string, fret, NOTE_NAMES[(exercise.tuning[string] + fret) % 12], BLUE))
        self.fretboard.set_marks(marks)

    def _show_result(self, result: StepResult) -> None:
        self.tab.set_verdict(self.offset + result.index, result.verdict)
        text = VERDICT_TEXT[result.verdict]
        if result.played is not None:
            if result.verdict is Verdict.WRONG:
                text += f": heard {midi_name(result.played.midi)}"
            elif result.verdict is Verdict.OUT_OF_TUNE:
                text += f" ({result.played.cents:+.0f} cents)"
            self._last_played = (result.played, result.verdict)
        self._set_feedback(text, result.verdict)

    def _finish(self) -> None:
        session = self.session
        if session is None:
            return
        self._timer.stop()
        self.session = None
        summary = session.summary()
        if summary.total:
            self.history.add(SessionRecord(
                session.exercise.title, datetime.now().isoformat(timespec="seconds"), session.bpm,
                summary.total, summary.correct, summary.mean_abs_timing_ms,
            ))
            self._show_record()
        step = self.tempo_step.value() if self.adapt.isChecked() else 5
        goal = self.goal.value() if self.adapt.isChecked() else None
        suggested = next_tempo(session.bpm, summary.accuracy, step=step, target=goal)
        if self.loop.isChecked():
            self.runs += 1
            if self.adapt.isChecked():
                self.bpm.setValue(suggested)
            change = "" if not self.adapt.isChecked() or suggested == session.bpm else f" → {suggested} BPM"
            self._set_feedback(f"Run {self.runs}: {summary.accuracy:.0%}{change}", None)
            self.target.setText("–")
            self.position.setText("Next run starts in a moment")
            self._restart.start()
            return
        if self._started_metronome:
            self.metronome.stop()
            self._started_metronome = False
        self.stop()
        self._show_summary(session, summary, suggested)

    def _loop_again(self) -> None:
        runs = self.runs
        if self._started_metronome:
            self.metronome.stop()
            self._started_metronome = False
        self.start()
        self.runs = runs

    def _show_summary(self, session: PracticeSession, summary, suggested: int) -> None:
        self.tab.set_current(None)
        self.fretboard.set_marks([])
        self.result_score.setText(f"{summary.accuracy:.0%}")
        if summary.accuracy >= SPEED_UP_AT:
            caption = "Clean run. Time to push the tempo."
        elif summary.accuracy < BACK_OFF_BELOW:
            caption = "Slow it down until it feels easy."
        else:
            caption = "Getting there. Same tempo again."
        self.result_caption.setText(caption)
        labels = {
            Verdict.CORRECT: f"{summary.correct} correct",
            Verdict.OUT_OF_TUNE: f"{summary.out_of_tune} out of tune",
            Verdict.WRONG: f"{summary.wrong} wrong",
            Verdict.MISSED: f"{summary.missed} missed",
        }
        for verdict, chip in self.result_chips.items():
            chip.setText(labels[verdict])
        detail = [f"{summary.correct}/{summary.total} notes at {session.bpm:.0f} BPM."]
        if summary.mean_abs_timing_ms is not None:
            detail.append(f"Average timing offset {summary.mean_abs_timing_ms:.0f} ms.")
        self.result_detail.setText(" ".join(detail))
        self.result_tab.set_exercise(self.exercise)
        if self.offset or len(session.exercise.steps) != len(self.exercise.steps):
            self.result_tab.set_range(self.offset, self.offset + len(session.exercise.steps) - 1)
        for index, verdict in self.tab.verdicts.items():
            self.result_tab.set_verdict(index, verdict)
        # Scroll so the start of the run is in view.
        self.result_tab.set_current(None)
        self.suggested_bpm = suggested
        if suggested == int(session.bpm):
            self.suggested_button.setText(f"Again at {suggested} BPM")
        else:
            verb = "Faster" if suggested > session.bpm else "Slower"
            self.suggested_button.setText(f"{verb}: {suggested} BPM")
        self.views.setCurrentWidget(self.results_view)


# ------------------------------------------------------------------- Library

class PasteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paste a tab")
        self.resize(720, 480)
        self.title = QComboBox()
        self.title.setEditable(True)
        self.title.setCurrentText("My tab")
        self.text = QPlainTextEdit()
        self.text.setFont(mono_font())
        self.text.setPlaceholderText("e|-----0---|\nB|---1-----|\nG|-0-------|\nD|---------|\nA|---------|\nE|---------|")
        help_text = QLabel("Paste a standard six-line ASCII tab. Numbers are read in column order; "
                           "rhythm, bends and slides are ignored. Chords count as one step.")
        help_text.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QFormLayout(self)
        layout.addRow("Title", self.title)
        layout.addRow(help_text)
        layout.addRow(self.text)
        layout.addRow(buttons)


class LibraryPage(QWidget):
    practice_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self.generated: list[Exercise] = []

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.on_select)
        self.list.itemDoubleClicked.connect(lambda _item: self.practice())
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(mono_font())
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        practice = QPushButton("Practice")
        practice.clicked.connect(self.practice)
        self.save_button = QPushButton("Save to my songs")
        self.save_button.clicked.connect(self.save_selected)
        paste = QPushButton("Paste tab…")
        paste.clicked.connect(self.paste)
        import_button = QPushButton("Import .tab…")
        import_button.clicked.connect(self.import_file)
        folder = QPushButton("Open folder")
        folder.clicked.connect(self.open_folder)
        # Managing the library sits under the list; acting on the selection sits under the preview.
        manage = QHBoxLayout()
        for button in (paste, import_button, folder):
            manage.addWidget(button)
        manage.addStretch(1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.list)
        left_layout.addLayout(manage)

        buttons = QHBoxLayout()
        for button in (practice, self.save_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.preview)
        right_layout.addLayout(buttons)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._build_generator())
        self.reload()

    def _build_generator(self) -> QGroupBox:
        box = QGroupBox("Generate an exercise")
        self.kind = QComboBox()
        self.kind.addItems(["Scale run", "Random melody", "Arpeggio", "Chromatic", "Find the note"])
        self.root = QComboBox()
        self.root.addItems(NOTE_NAMES)
        self.root.setCurrentText("A")
        self.scale = QComboBox()
        self.low_fret = QSpinBox()
        self.low_fret.setRange(-1, 15)
        self.low_fret.setSpecialValueText("Auto")
        self.low_fret.setValue(-1)
        self.low_fret.setToolTip("Lowest fret of the hand position. Auto starts near the root on the low E string.")
        self.group = QSpinBox()
        self.group.setRange(1, 4)
        self.group.setToolTip("Play the scale in groups: 3 means 1-2-3, 2-3-4, …")
        self.length = QSpinBox()
        self.length.setRange(4, 64)
        self.length.setValue(16)
        generate = QPushButton("Generate")
        generate.clicked.connect(self.generate)
        self.kind.currentIndexChanged.connect(self._update_generator_fields)

        grid = QGridLayout(box)
        labels = ("Type", "Root", "Scale / chord", "Position", "Groups", "Notes")
        widgets = (self.kind, self.root, self.scale, self.low_fret, self.group, self.length)
        self._generator_fields = dict(zip(labels, widgets))
        # Two rows of three fields so the box fits narrow windows.
        for index, (label, widget) in enumerate(zip(labels, widgets)):
            row, column = divmod(index, 3)
            if isinstance(widget, QComboBox):
                widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                widget.setMinimumContentsLength(10)
            grid.addWidget(QLabel(label), row * 2, column)
            grid.addWidget(widget, row * 2 + 1, column)
        grid.addWidget(generate, 3, 3)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        self._update_generator_fields()
        return box

    def _update_generator_fields(self) -> None:
        kind = self.kind.currentText()
        self.scale.blockSignals(True)
        self.scale.clear()
        if kind == "Arpeggio":
            self.scale.addItems(list(CHORDS))
        else:
            self.scale.addItems([s for s in SCALES if s != "chromatic"])
            self.scale.setCurrentText("minor pentatonic")
        self.scale.blockSignals(False)
        self.root.setEnabled(kind != "Chromatic")
        self.scale.setEnabled(kind in ("Scale run", "Random melody", "Arpeggio"))
        self.group.setEnabled(kind == "Scale run")
        self.length.setEnabled(kind == "Random melody")
        self.low_fret.setEnabled(kind != "Find the note")

    def generate(self) -> None:
        kind = self.kind.currentText()
        low = None if self.low_fret.value() < 0 else self.low_fret.value()
        root, scale = self.root.currentText(), self.scale.currentText()
        try:
            if kind == "Scale run":
                exercise = generator.scale_run(root, scale, low_fret=low, group=self.group.value())
            elif kind == "Random melody":
                exercise = generator.random_melody(root, scale, length=self.length.value(), low_fret=low)
            elif kind == "Arpeggio":
                exercise = generator.arpeggio(root, scale, low_fret=low)
            elif kind == "Chromatic":
                exercise = generator.chromatic(start_fret=max(1, low or 1))
            else:
                exercise = generator.note_finder(root)
        except ValueError as error:
            QMessageBox.information(self, "Generate", str(error))
            return
        self.add_generated(exercise)

    def add_generated(self, exercise: Exercise) -> None:
        self.generated.insert(0, exercise)
        self.reload(select=exercise)

    def reload(self, select: Exercise | None = None) -> None:
        exercises, errors = load_library()
        self.list.clear()
        for group, items in (("Generated", self.generated), ("Library", exercises)):
            if not items:
                continue
            header = QListWidgetItem(group)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setFont(big_font(10))
            self.list.addItem(header)
            for exercise in items:
                item = QListWidgetItem(exercise.title)
                item.setData(Qt.ItemDataRole.UserRole, exercise)
                self.list.addItem(item)
                if exercise is select:
                    self.list.setCurrentItem(item)
        if select is None and self.list.count() > 1:
            self.list.setCurrentRow(1)  # row 0 is a group header
        if errors:
            self.preview.setPlainText("Some files could not be read:\n" + "\n".join(errors))

    def selected(self) -> Exercise | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def on_select(self, *_args) -> None:
        exercise = self.selected()
        if exercise is None:
            return
        self.preview.setPlainText(render_tab(exercise))
        self.save_button.setEnabled(exercise.source == "generated" or not exercise.source)

    def practice(self) -> None:
        exercise = self.selected()
        if exercise is not None:
            self.practice_requested.emit(exercise)

    def save_selected(self) -> None:
        exercise = self.selected()
        if exercise is None:
            return
        folder = user_dir()
        folder.mkdir(parents=True, exist_ok=True)
        stem = "".join(c if c.isalnum() else "-" for c in exercise.title.lower()).strip("-")
        path = folder / f"{stem}.tab"
        path.write_text(render_tab(exercise), encoding="utf-8")
        if exercise in self.generated:
            self.generated.remove(exercise)
        self.reload()
        QMessageBox.information(self, "Saved", f"Saved to {path}")

    def paste(self) -> None:
        dialog = PasteDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            exercise = parse_tab(dialog.text.toPlainText())
        except (TabError, ValueError) as error:
            QMessageBox.warning(self, "Tab", f"Could not read the tab: {error}")
            return
        exercise.title = dialog.title.currentText().strip() or "Pasted tab"
        exercise.source = "generated"
        self.add_generated(exercise)

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import exercise",
            str(Path.home()),
            "Exercise files (*.tab *.txt *.gp3 *.gp4 *.gp5 *.musicxml *.xml)",
        )
        if not path:
            return
        try:
            source_path = Path(path)
            if source_path.suffix.lower() in {".tab", ".txt"}:
                exercises = [parse_tab(source_path.read_text(encoding="utf-8"), source=path)]
            else:
                exercises = load_import(source_path)
        except (ImportError, TabError, ValueError, OSError) as error:
            QMessageBox.warning(self, "Import", f"Could not read the exercise: {error}")
            return
        folder = user_dir()
        folder.mkdir(parents=True, exist_ok=True)
        if len(exercises) == 1:
            exercise = exercises[0]
        else:
            labels = [exercise.title for exercise in exercises]
            selected, accepted = QInputDialog.getItem(self, "Choose track", "Track or part:", labels, 0, False)
            if not accepted:
                return
            exercise = exercises[labels.index(selected)]
        if source_path.suffix.lower() == ".tab":
            shutil.copy(path, folder / source_path.name)
        else:
            stem = "".join(c if c.isalnum() else "-" for c in exercise.title.lower()).strip("-") or source_path.stem
            (folder / f"{stem}.tab").write_text(render_tab(exercise), encoding="utf-8")
        self.reload()

    def open_folder(self) -> None:
        folder = user_dir()
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(folder)])


# -------------------------------------------------------------------- Theory

class TheoryPage(QWidget):
    practice_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self.mode = QComboBox()
        self.mode.addItems(["Scale", "Chord"])
        self.root = QComboBox()
        self.root.addItems(NOTE_NAMES)
        self.kind = QComboBox()
        practice = QPushButton("Practice this")
        practice.clicked.connect(self.practice)
        controls = QHBoxLayout()
        for widget in (self.mode, self.root, self.kind):
            controls.addWidget(widget)
        controls.addStretch(1)
        controls.addWidget(practice)

        self.heading = QLabel()
        self.heading.setFont(big_font(18))
        self.about = QLabel()
        self.about.setWordWrap(True)
        self.notes = QLabel()
        self.notes.setFont(mono_font(12))
        self.notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.chords = QLabel()
        self.chords.setWordWrap(True)
        self.fretboard = Fretboard(frets=15)
        legend = QLabel("Blue: root. Green: other notes. Use the fretboard to find the same shape in other keys: move it, the pattern stays.")
        legend.setWordWrap(True)
        color_label(legend, GREY)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.heading)
        layout.addWidget(self.about)
        layout.addWidget(self.notes)
        layout.addWidget(self.chords)
        layout.addWidget(self.fretboard, 1)
        layout.addWidget(legend)

        self.mode.currentIndexChanged.connect(self._fill_kinds)
        self.root.currentIndexChanged.connect(self.refresh)
        self.kind.currentIndexChanged.connect(self.refresh)
        self._fill_kinds()

    def _fill_kinds(self) -> None:
        self.kind.blockSignals(True)
        self.kind.clear()
        self.kind.addItems(list(SCALES) if self.mode.currentText() == "Scale" else list(CHORDS))
        self.kind.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        root = self.root.currentIndex()
        kind = self.kind.currentText()
        if not kind:
            return
        is_scale = self.mode.currentText() == "Scale"
        pcs = scale_pitch_classes(root, kind) if is_scale else chord_pitch_classes(root, kind)
        formula = SCALES[kind] if is_scale else CHORDS[kind]
        self.heading.setText(f"{NOTE_NAMES[root]} {kind}")
        if is_scale:
            self.about.setText(f"{SCALE_NOTES.get(kind, '')}\nSteps: {step_pattern(kind)}  (W = whole step, 2 frets; H = half step, 1 fret)")
        else:
            self.about.setText("Chord tones, from the root. Stack them in any order and octave; the chord name stays the same.")
        rows = [f"{NOTE_NAMES[pc]:<3} {interval_name(step)}" for pc, step in zip(pcs, formula)]
        self.notes.setText("\n".join(rows))
        if is_scale and len(pcs) == 7:
            triads = diatonic_triads(root, kind)
            numerals = []
            for chord in triads:
                numeral = ROMAN[chord.degree - 1]
                if chord.quality != "major":
                    numeral = numeral.lower() + ("°" if chord.quality == "diminished" else "")
                numerals.append(f"{numeral} {chord.name}")
            self.chords.setText("Chords in this key:  " + "   ".join(numerals))
        else:
            self.chords.setText("")
        marks = [
            FretMark(p.string, p.fret, NOTE_NAMES[p.midi % 12], BLUE if p.midi % 12 == root else GREEN)
            for p in fret_positions(pcs, max_fret=self.fretboard.frets)
        ]
        self.fretboard.set_marks(marks)

    def practice(self) -> None:
        root = self.root.currentIndex()
        kind = self.kind.currentText()
        try:
            if self.mode.currentText() == "Scale":
                exercise = generator.scale_run(root, kind)
            else:
                exercise = generator.arpeggio(root, kind)
        except ValueError as error:
            QMessageBox.information(self, "Practice", str(error))
            return
        self.practice_requested.emit(exercise)


# -------------------------------------------------------------- Main window

NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("home", "Home"),
    ("library", "Library"),
    ("practice", "Practice"),
    ("tuner", "Tuner"),
    ("metronome", "Metronome"),
    ("theory", "Theory"),
    ("quiz", "Quiz"),
    ("progress", "Progress"),
)


RAIL_WIDE = 176
RAIL_COMPACT = 64
# Below this window width the rail shows icons only (names stay as tooltips and accessible names).
COMPACT_BELOW = 880


class MainWindow(QMainWindow):
    def __init__(self, history: History | None = None, start_audio: bool = True):
        super().__init__()
        self.setWindowTitle("Guitar Practice")
        self.setMinimumSize(760, 600)
        self.resize(1000, 720)
        app = QApplication.instance()
        if app is not None and not app.property("guitarapp_themed"):
            apply_theme(app)
            app.setProperty("guitarapp_themed", True)

        self.hub = AudioHub(self)
        self.bridge = BeatBridge(self)
        self.metronome = Metronome(SAMPLE_RATE, on_beat=self.bridge.beat.emit)

        self.history = history if history is not None else History()
        self.home_page = HomePage(self.history)
        self.practice_page = PracticePage(self.hub, self.metronome, self.history)
        self.tuner_page = TunerPage(self.hub)
        self.metronome_page = MetronomePage(self.metronome, self.bridge)
        self.library_page = LibraryPage()
        self.theory_page = TheoryPage()
        self.quiz_page = QuizPage(self.hub)
        self.progress_page = ProgressPage(self.history)
        self.library_page.practice_requested.connect(self.open_practice)
        self.theory_page.practice_requested.connect(self.open_practice)
        self.home_page.route_requested.connect(self.show_route)
        self.practice_page.library_requested.connect(lambda: self.show_route("library"))

        self.pages: dict[str, QWidget] = {
            "home": self.home_page,
            "library": self.library_page,
            "practice": self.practice_page,
            "tuner": self.tuner_page,
            "metronome": self.metronome_page,
            "theory": self.theory_page,
            "quiz": self.quiz_page,
            "progress": self.progress_page,
        }
        self.stack = QStackedWidget()
        self.stack.setObjectName("Pages")
        self.stack.setContentsMargins(16, 8, 16, 4)
        for page in self.pages.values():
            # The stack owns the page gutter, so pages drop their own layout margins.
            if page.layout() is not None:
                page.layout().setContentsMargins(0, 0, 0, 0)
            self.stack.addWidget(page)

        shell = QWidget()
        shell.setObjectName("Shell")
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_nav())
        row.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self._build_toolbar()

        self.space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        # One press, one action: a held Space must not re-click buttons or flap the metronome.
        self.space_shortcut.setAutoRepeat(False)
        self.space_shortcut.activated.connect(self.on_space)
        self.hub.status.connect(self.statusBar().showMessage)
        self.hub.frame.connect(lambda _pitch, level: self.level.set_level(level))
        self.current_route = ""
        self.show_route("home")
        self.home_page.cards[0].setFocus()
        self.toggle_mic(start_audio)

    def _build_nav(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("NavRail")
        rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        rail.setFixedWidth(RAIL_WIDE)
        self.rail = rail
        column = QVBoxLayout(rail)
        column.setContentsMargins(12, 18, 12, 18)
        column.setSpacing(4)
        self.brand = QLabel("Guitar Practice")
        self.brand.setObjectName("Brand")
        column.addWidget(self.brand)
        self.route_buttons: dict[str, QPushButton] = {}
        for route, label in NAV_ITEMS:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setAccessibleName(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(tool_icon(route, 20, PALETTE["cream"], PALETTE["navy"]))
            button.setIconSize(QSize(20, 20))
            button.setToolTip(label)
            button.clicked.connect(lambda _checked=False, r=route: self.show_route(r))
            self.route_buttons[route] = button
            column.addWidget(button)
        column.addStretch(1)
        return rail

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._set_rail_compact(self.width() < COMPACT_BELOW)

    def _set_rail_compact(self, compact: bool) -> None:
        if self.rail.property("compact") == compact:
            return
        self.rail.setProperty("compact", compact)
        self.rail.setFixedWidth(RAIL_COMPACT if compact else RAIL_WIDE)
        self.brand.setText("GP" if compact else "Guitar Practice")
        self.brand.setAlignment(Qt.AlignmentFlag.AlignCenter if compact else Qt.AlignmentFlag.AlignLeft)
        for (route, label), button in zip(NAV_ITEMS, self.route_buttons.values()):
            button.setText("" if compact else label)
            button.setProperty("compact", compact)
            button.style().unpolish(button)
            button.style().polish(button)

    def show_route(self, route: str) -> None:
        page = self.pages[route]
        self.current_route = route
        # Checked state is set by hand: an exclusive QButtonGroup would drop
        # Tab focus from every unchecked button.
        for name, button in self.route_buttons.items():
            button.setChecked(name == route)
        self.stack.setCurrentWidget(page)
        if route == "home":
            self.home_page.refresh()

    def _build_toolbar(self) -> None:
        bar = QToolBar("Audio")
        bar.setMovable(False)
        self.addToolBar(bar)
        self.listen = QPushButton("Listening")
        self.listen.setCheckable(True)
        self.listen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.listen.toggled.connect(self.toggle_mic)
        self.device = QComboBox()
        self.device.setMaximumWidth(320)
        self.device.addItem("Default input", None)
        try:
            for index, name in input_devices():
                self.device.addItem(name, index)
        except Exception as error:
            self.statusBar().showMessage(f"Audio devices unavailable: {error}")
        self.device.currentIndexChanged.connect(lambda _i: self.toggle_mic(True))
        self.level = LevelMeter()
        bar.addWidget(self.listen)
        bar.addWidget(QLabel("  Input "))
        bar.addWidget(self.device)
        bar.addWidget(QLabel("  "))
        bar.addWidget(self.level)

    def toggle_mic(self, on: bool) -> None:
        if on:
            ok = self.hub.start(self.device.currentData())
        else:
            self.hub.stop()
            self.level.set_level(0.0)
            self.statusBar().showMessage("Microphone off")
            ok = False
        self.listen.blockSignals(True)
        self.listen.setChecked(ok)
        self.listen.setText("Listening" if ok else "Mic off")
        self.listen.blockSignals(False)
        self.home_page.set_microphone_state(ok)

    def open_practice(self, exercise: Exercise) -> None:
        self.practice_page.load(exercise)
        self.show_route("practice")

    def on_space(self) -> None:
        if self.current_route == "metronome":
            self.metronome_page.toggle()
        elif self.current_route == "practice" and self.practice_page.exercise is not None:
            self.practice_page.toggle()
        else:
            # The window-wide shortcut swallows Space; keep it activating the focused button.
            focus = QApplication.focusWidget()
            if isinstance(focus, QAbstractButton) and focus.isEnabled():
                focus.animateClick()

    def closeEvent(self, event) -> None:
        self.practice_page.stop()
        self.metronome.stop()
        self.hub.stop()
        super().closeEvent(event)


def run() -> int:
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName("guitar-app")
    app.setApplicationDisplayName("Guitar Practice")
    app.setDesktopFileName("guitar-app")
    apply_theme(app)
    app.setProperty("guitarapp_themed", True)
    window = MainWindow()
    window.show()
    return app.exec()

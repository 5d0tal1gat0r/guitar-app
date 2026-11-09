"""Main window: a navigation rail around Home, Practice, Library, Tuner, Metronome, Theory, Quiz and Progress."""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QInputDialog, QMessageBox, QPlainTextEdit, QPushButton, QSlider, QSpinBox, QSplitter, QTabWidget,
    QStackedWidget, QToolBar, QVBoxLayout, QWidget, QAbstractButton,
)

from . import generator
from .audio import MicInput, input_devices
from .importers import load_import
from .history import History, SessionRecord
from .home import HomePage
from .metronome import MAX_BPM, MIN_BPM, Metronome, TapTempo
from .pitch import NoteReading, NoteTracker, Pitch, detect_pitch, reading_from_freq, rms
from .practice import PracticeSession, StepResult, Verdict
from .theme import PALETTE, apply_theme, tool_icon
from .tabs import Exercise, TabError, load_library, parse_tab, render_tab, user_dir
from .trainer_ui import ProgressPage, QuizPage
from .theory import (
    CHORDS, NOTE_NAMES, SCALES, STANDARD_TUNING, STRING_NAMES, chord_pitch_classes,
    diatonic_triads, fret_for_midi, fret_positions, interval_name, midi_name, scale_pitch_classes,
)
from .widgets import BLUE, GREEN, GREY, RED, VERDICT_COLORS, CentsMeter, Fretboard, FretMark, LevelMeter, StepStrip

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
    def __init__(self, hub: AudioHub, metronome: Metronome, history: History):
        super().__init__()
        self.hub = hub
        self.metronome = metronome
        self.history = history
        self.exercise: Exercise | None = None
        self.session: PracticeSession | None = None
        self._started_metronome = False
        self._last_played: tuple[NoteReading, Verdict] | None = None

        self.title = QLabel("Pick an exercise in the Library, or generate one")
        self.title.setFont(big_font(15))
        self.description = QLabel("")
        self.description.setWordWrap(True)
        color_label(self.description, GREY)
        self.record = QLabel("")
        color_label(self.record, GREY)

        self.target = QLabel("–")
        self.target.setFont(big_font(48))
        self.position = QLabel(" ")
        self.feedback = QLabel(" ")
        self.feedback.setFont(big_font(15))
        target_box = QVBoxLayout()
        target_box.addWidget(QLabel("Play"))
        target_box.addWidget(self.target)
        target_box.addWidget(self.position)
        target_box.addWidget(self.feedback)

        self.heard = QLabel("–")
        self.heard.setFont(big_font(28, bold=False))
        heard_box = QVBoxLayout()
        heard_box.addWidget(QLabel("Hearing"))
        heard_box.addWidget(self.heard)
        heard_box.addStretch(1)

        top = QHBoxLayout()
        top.addLayout(target_box, 2)
        top.addLayout(heard_box, 1)

        self.fretboard = Fretboard(frets=15)
        self.strip = StepStrip()

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
        self.start_button = QPushButton("Start")
        self.start_button.setFont(big_font(13))
        self.start_button.setMinimumHeight(40)
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.toggle)
        controls = QHBoxLayout()
        for widget in (QLabel("Tempo"), self.bpm, QLabel("Tolerance"), self.tolerance, self.ignore_octave, self.click):
            controls.addWidget(widget)
        controls.addStretch(1)
        controls.addWidget(self.start_button)

        self.result = QLabel(" ")
        self.result.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.description)
        layout.addWidget(self.record)
        layout.addSpacing(6)
        layout.addLayout(top)
        layout.addWidget(self.fretboard, 1)
        layout.addWidget(self.strip)
        layout.addWidget(self.result)
        layout.addLayout(controls)

        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._tick)
        hub.note.connect(self.on_note)
        hub.frame.connect(self.on_frame)

    def load(self, exercise: Exercise) -> None:
        self.stop()
        self.exercise = exercise
        self.title.setText(exercise.title)
        self.description.setText(exercise.description)
        self._show_record()
        self.bpm.setValue(exercise.bpm)
        self.strip.set_steps([" ".join(midi_name(m) for m in exercise.midi_notes(s)) for s in exercise.steps])
        self.start_button.setEnabled(True)
        self.result.setText(f"{len(exercise.steps)} notes. Press Start; a one-bar count-in comes first.")
        color_label(self.result, None)
        self._show_step(0)

    def _show_record(self) -> None:
        stats = self.history.stats(self.exercise.title) if self.exercise else None
        if stats is None:
            self.record.setText("Not played yet")
            return
        clean = f", fastest clean run {stats.best_clean_bpm:.0f} BPM" if stats.best_clean_bpm else ""
        self.record.setText(f"Played {stats.sessions}×, best {stats.best_accuracy:.0%}{clean}")

    def toggle(self) -> None:
        if self.session is None:
            self.start()
        else:
            self.stop()
            self.result.setText("Stopped.")

    def start(self) -> None:
        if self.exercise is None:
            return
        if not self.hub.running and not self.hub.start():
            QMessageBox.warning(self, "Microphone", "The microphone could not be opened. Check the input device in the toolbar.")
            return
        bpm = self.bpm.value()
        beats_per_bar = 4
        origin = time.monotonic()
        if self.click.isChecked():
            if self.metronome.running:
                self.metronome.stop()
            clock = self.metronome.clock
            clock.bpm, clock.beats_per_bar, clock.subdivision = bpm, beats_per_bar, 1
            try:
                self.metronome.start()
                self._started_metronome = True
                origin = time.monotonic() + self.metronome.output_latency()
            except Exception as error:
                self.result.setText(f"No click: audio output failed ({error}).")
        self.session = PracticeSession(
            self.exercise,
            start_time=origin + beats_per_bar * 60.0 / bpm,
            bpm=bpm,
            tolerance_cents=self.tolerance.value(),
            ignore_octave=self.ignore_octave.isChecked(),
        )
        self.strip.set_steps(self.strip.labels)
        self._last_played = None
        self.feedback.setText("Count-in…")
        color_label(self.feedback, GREY)
        self.result.setText(" ")
        self.start_button.setText("Stop")
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.session = None
        if self._started_metronome:
            self.metronome.stop()
            self._started_metronome = False
        self.start_button.setText("Start")

    def on_frame(self, pitch: Pitch | None, _level: float) -> None:
        if self.isVisible():
            self.heard.setText(midi_name(reading_from_freq(pitch.freq).midi) if pitch else "–")

    def on_note(self, reading: NoteReading) -> None:
        if self.session is None:
            return
        result = self.session.on_note(time.monotonic(), reading)
        if result is not None:
            self._show_result(result)

    def _tick(self) -> None:
        session = self.session
        if session is None:
            return
        now = time.monotonic()
        for result in session.advance(now):
            if result.verdict is Verdict.MISSED:
                self._show_result(result)
        if session.finished:
            self._finish()
            return
        index = len(session.results)
        if now >= session.step_start(0) - session.early:
            self._show_step(index)
            if self.feedback.text() == "Count-in…":
                self.feedback.setText(" ")
        else:
            beats_left = int((session.step_start(0) - now) / session.seconds_per_beat) + 1
            self.position.setText(f"Starting in {beats_left}")

    def _show_step(self, index: int) -> None:
        exercise = self.exercise
        if exercise is None or index >= len(exercise.steps):
            return
        step = exercise.steps[index]
        self.target.setText(" + ".join(midi_name(m) for m in exercise.midi_notes(step)))
        self.position.setText(position_text(exercise, step.notes))
        self.strip.set_current(index)
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
        self.strip.set_verdict(result.index, result.verdict)
        text = VERDICT_TEXT[result.verdict]
        if result.played is not None:
            if result.verdict is Verdict.WRONG:
                text += f": heard {midi_name(result.played.midi)}"
            elif result.verdict is Verdict.OUT_OF_TUNE:
                text += f" ({result.played.cents:+.0f} cents)"
            self._last_played = (result.played, result.verdict)
        self.feedback.setText(text)
        color_label(self.feedback, VERDICT_COLORS[result.verdict])

    def _finish(self) -> None:
        session = self.session
        self.stop()
        if session is None:
            return
        summary = session.summary()
        if summary.total:
            self.history.add(SessionRecord(
                session.exercise.title, datetime.now().isoformat(timespec="seconds"), session.bpm,
                summary.total, summary.correct, summary.mean_abs_timing_ms,
            ))
            self._show_record()
        self.strip.set_current(None)
        self.target.setText("–")
        self.position.setText(" ")
        self.fretboard.set_marks([])
        lines = [
            f"{summary.accuracy:.0%} correct ({summary.correct}/{summary.total}).",
            f"Wrong {summary.wrong}, out of tune {summary.out_of_tune}, missed {summary.missed}.",
        ]
        if summary.mean_abs_timing_ms is not None:
            lines.append(f"Average timing offset {summary.mean_abs_timing_ms:.0f} ms.")
        if summary.accuracy >= 0.9:
            lines.append(f"Clean. Try {session.bpm + 5:.0f} BPM.")
            self.bpm.setValue(int(session.bpm) + 5)
            color_label(self.result, GREEN)
        elif summary.accuracy < 0.6:
            lines.append(f"Slow down: try {max(MIN_BPM, session.bpm - 10):.0f} BPM until it is clean.")
            color_label(self.result, RED)
        else:
            color_label(self.result, None)
        self.result.setText("  ".join(lines))
        self.feedback.setText("Done")
        color_label(self.feedback, None)


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
        buttons = QHBoxLayout()
        for button in (practice, self.save_button, paste, import_button, folder):
            buttons.addWidget(button)
        buttons.addStretch(1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.preview)
        right_layout.addLayout(buttons)

        splitter = QSplitter()
        splitter.addWidget(self.list)
        splitter.addWidget(right)
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
        for column, (label, widget) in enumerate(zip(labels, widgets)):
            grid.addWidget(QLabel(label), 0, column)
            grid.addWidget(widget, 1, column)
        grid.addWidget(generate, 1, len(labels))
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


class MainWindow(QMainWindow):
    def __init__(self, history: History | None = None, start_audio: bool = True):
        super().__init__()
        self.setWindowTitle("Guitar Practice")
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
        for page in self.pages.values():
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

        space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        space.activated.connect(self.on_space)
        self.hub.status.connect(self.statusBar().showMessage)
        self.hub.frame.connect(lambda _pitch, level: self.level.set_level(level))
        self.current_route = ""
        self.show_route("home")
        self.toggle_mic(start_audio)

    def _build_nav(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("NavRail")
        rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        rail.setFixedWidth(176)
        column = QVBoxLayout(rail)
        column.setContentsMargins(12, 18, 12, 18)
        column.setSpacing(4)
        brand = QLabel("Guitar Practice")
        brand.setObjectName("Brand")
        column.addWidget(brand)
        self.route_buttons: dict[str, QPushButton] = {}
        for route, label in NAV_ITEMS:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setAccessibleName(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(tool_icon(route, 20, PALETTE["cream"], PALETTE["navy"]))
            button.clicked.connect(lambda _checked=False, r=route: self.show_route(r))
            self.route_buttons[route] = button
            column.addWidget(button)
        column.addStretch(1)
        return rail

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

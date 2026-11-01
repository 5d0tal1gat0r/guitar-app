"""Music theory core: note names, frequencies, scales, chords and fretboard maps.

Pitches are MIDI numbers (E2 = 40, A4 = 69). Pitch classes are 0-11 (C = 0).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
INTERVAL_NAMES = (
    "unison", "minor 2nd", "major 2nd", "minor 3rd", "major 3rd", "perfect 4th",
    "tritone", "perfect 5th", "minor 6th", "major 6th", "minor 7th", "major 7th",
)
A4_MIDI = 69
A4_HZ = 440.0

# Low E to high E, as MIDI numbers.
STANDARD_TUNING = (40, 45, 50, 55, 59, 64)
STRING_NAMES = ("E", "A", "D", "G", "B", "e")

SCALES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "natural minor": (0, 2, 3, 5, 7, 8, 10),
    "harmonic minor": (0, 2, 3, 5, 7, 8, 11),
    "major pentatonic": (0, 2, 4, 7, 9),
    "minor pentatonic": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "chromatic": tuple(range(12)),
}

# Chord quality -> semitones above the root.
CHORDS: dict[str, tuple[int, ...]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "diminished": (0, 3, 6),
    "augmented": (0, 4, 8),
    "dominant 7": (0, 4, 7, 10),
    "major 7": (0, 4, 7, 11),
    "minor 7": (0, 3, 7, 10),
    "sus4": (0, 5, 7),
}

_LETTER_TO_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")
_PC_RE = re.compile(r"^([A-Ga-g])([#b]?)$")


def parse_pitch_class(text: str) -> int:
    """Parse 'C', 'F#', 'Bb' (or 'A#') into a pitch class 0-11."""
    match = _PC_RE.match(text.strip())
    if not match:
        raise ValueError(f"not a note name: {text!r}")
    letter, accidental = match.group(1).upper(), match.group(2)
    return (_LETTER_TO_PC[letter] + _accidental_offset(accidental)) % 12


def parse_note(text: str) -> int:
    """Parse scientific pitch notation ('E2', 'Bb3', 'F#4') into a MIDI number."""
    match = _NOTE_RE.match(text.strip())
    if not match:
        raise ValueError(f"not a note: {text!r}")
    letter, accidental, octave = match.group(1).upper(), match.group(2), int(match.group(3))
    return (octave + 1) * 12 + _LETTER_TO_PC[letter] + _accidental_offset(accidental)


def _accidental_offset(accidental: str) -> int:
    return {"": 0, "#": 1, "b": -1}[accidental]


def midi_name(midi: int) -> str:
    """MIDI number -> name with octave, e.g. 40 -> 'E2'."""
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def midi_to_freq(midi: float, a4_hz: float = A4_HZ) -> float:
    return a4_hz * 2.0 ** ((midi - A4_MIDI) / 12.0)


def freq_to_midi(freq: float, a4_hz: float = A4_HZ) -> float:
    """Fractional MIDI number for a frequency. Use cents_from_midi for the offset."""
    return A4_MIDI + 12.0 * math.log2(freq / a4_hz)


def cents_from_midi(freq: float, midi: int, a4_hz: float = A4_HZ) -> float:
    """How far `freq` sits from the equal-tempered `midi` note, in cents (+ = sharp)."""
    return (freq_to_midi(freq, a4_hz) - midi) * 100.0


def scale_pitch_classes(root: int | str, scale: str) -> tuple[int, ...]:
    """Pitch classes of a scale, starting from the root."""
    root_pc = parse_pitch_class(root) if isinstance(root, str) else root % 12
    return tuple((root_pc + step) % 12 for step in SCALES[scale])


def chord_pitch_classes(root: int | str, quality: str) -> tuple[int, ...]:
    root_pc = parse_pitch_class(root) if isinstance(root, str) else root % 12
    return tuple((root_pc + step) % 12 for step in CHORDS[quality])


def interval_name(semitones: int) -> str:
    """Interval name for a number of semitones, octaves folded into 0-11."""
    return INTERVAL_NAMES[semitones % 12]


@dataclass(frozen=True)
class DiatonicChord:
    degree: int  # 1-based scale degree
    root: int  # pitch class
    quality: str  # "major", "minor" or "diminished"

    @property
    def name(self) -> str:
        suffix = {"major": "", "minor": "m", "diminished": "dim"}[self.quality]
        return f"{NOTE_NAMES[self.root]}{suffix}"


def diatonic_triads(root: int | str, scale: str = "major") -> list[DiatonicChord]:
    """Triads built on each degree of a seven-note scale, by stacking thirds."""
    pcs = scale_pitch_classes(root, scale)
    if len(pcs) != 7:
        raise ValueError(f"diatonic triads need a seven-note scale, got {scale!r}")
    chords = []
    for index in range(7):
        third = (pcs[(index + 2) % 7] - pcs[index]) % 12
        fifth = (pcs[(index + 4) % 7] - pcs[index]) % 12
        quality = {(4, 7): "major", (3, 7): "minor", (3, 6): "diminished"}[(third, fifth)]
        chords.append(DiatonicChord(index + 1, pcs[index], quality))
    return chords


@dataclass(frozen=True)
class FretPosition:
    string: int  # 0 = low E
    fret: int
    midi: int


def fret_positions(
    pitch_classes: tuple[int, ...] | list[int] | set[int],
    tuning: tuple[int, ...] = STANDARD_TUNING,
    max_fret: int = 12,
) -> list[FretPosition]:
    """Every fret on every string whose note belongs to the given pitch classes."""
    wanted = set(pitch_classes)
    found = []
    for string_index, open_midi in enumerate(tuning):
        for fret in range(max_fret + 1):
            midi = open_midi + fret
            if midi % 12 in wanted:
                found.append(FretPosition(string_index, fret, midi))
    return found


def fret_for_midi(midi: int, tuning: tuple[int, ...] = STANDARD_TUNING, max_fret: int = 24) -> list[FretPosition]:
    """All places on the fretboard that produce this MIDI note."""
    return [
        FretPosition(string_index, midi - open_midi, midi)
        for string_index, open_midi in enumerate(tuning)
        if 0 <= midi - open_midi <= max_fret
    ]


def render_fretboard(
    root: int | str,
    scale: str,
    tuning: tuple[int, ...] = STANDARD_TUNING,
    max_fret: int = 12,
) -> str:
    """ASCII fretboard, high e on top. 'R' marks the root, '*' other scale notes."""
    root_pc = parse_pitch_class(root) if isinstance(root, str) else root % 12
    pcs = set(scale_pitch_classes(root_pc, scale))
    lines = ["  " + "".join(f"{fret:<4d}" for fret in range(max_fret + 1))]
    for string_index in reversed(range(len(tuning))):
        cells = []
        for fret in range(max_fret + 1):
            midi = tuning[string_index] + fret
            if midi % 12 == root_pc:
                mark = "R"
            elif midi % 12 in pcs:
                mark = "*"
            else:
                mark = "-"
            cells.append(f"{mark}---")
        lines.append(f"{STRING_NAMES[string_index]}|" + "".join(cells))
    return "\n".join(lines)

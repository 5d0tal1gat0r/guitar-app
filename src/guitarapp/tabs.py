"""Tab exercises: a plain-text ASCII tab format, parser, renderer and library loader.

File format (`.tab`), human-editable:

    # title: A minor pentatonic, box 1
    # bpm: 70
    # tuning: E2 A2 D3 G3 B3 E4      (optional, low to high; default standard)
    # beats-per-note: 1              (optional; default 1)
    e|-----------5-8-|
    B|---------5-8---|
    ...

Rhythm is not read from dash spacing (hand-written tabs are rarely consistent).
Each column where a fret number starts is one step of `beats-per-note` beats;
fret numbers in the same column on several strings form a chord. Blank lines
separate tab systems, which are read in order. Letters such as h, p, b, / or x
are ignored, so most tabs from the web parse as a plain note sequence.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .theory import STANDARD_TUNING, STRING_NAMES, midi_name, parse_note

_LINE_RE = re.compile(r"^\s*([A-Ga-g][#b]?)\s*\|(.*)$")
_FRET_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class Step:
    beat: float
    notes: tuple[tuple[int, int], ...]  # (string, fret); string 0 = lowest


@dataclass
class Exercise:
    title: str
    steps: list[Step]
    bpm: int = 80
    tuning: tuple[int, ...] = STANDARD_TUNING
    description: str = ""
    source: str = ""  # file path, or "generated"
    beats_per_note: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)

    def midi_notes(self, step: Step) -> tuple[int, ...]:
        return tuple(self.tuning[string] + fret for string, fret in step.notes)

    def describe_step(self, step: Step) -> str:
        return " + ".join(midi_name(m) for m in self.midi_notes(step))

    @property
    def length_beats(self) -> float:
        return self.steps[-1].beat + self.beats_per_note if self.steps else 0.0


class TabError(ValueError):
    pass


def parse_tab(text: str, source: str = "") -> Exercise:
    meta: dict[str, str] = {}
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("#"):
            key, _, value = line.lstrip()[1:].partition(":")
            if value:
                meta[key.strip().lower()] = value.strip()
            continue
        match = _LINE_RE.match(line)
        if match:
            current.append(match.group(2))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    tuning = tuple(parse_note(n) for n in meta["tuning"].split()) if "tuning" in meta else STANDARD_TUNING
    beats_per_note = float(meta.get("beats-per-note", 1))
    steps: list[Step] = []
    for block in blocks:
        if len(block) != len(tuning):
            raise TabError(f"tab system has {len(block)} strings, tuning has {len(tuning)}")
        columns: dict[int, list[tuple[int, int]]] = {}
        # Tabs list the highest string first.
        for row, content in enumerate(block):
            string = len(tuning) - 1 - row
            for fret in _FRET_RE.finditer(content):
                columns.setdefault(fret.start(), []).append((string, int(fret.group())))
        for column in sorted(columns):
            steps.append(Step(len(steps) * beats_per_note, tuple(sorted(columns[column]))))
    if not steps:
        raise TabError("no notes found")
    return Exercise(
        title=meta.get("title", Path(source).stem if source else "Untitled"),
        steps=steps,
        bpm=int(meta.get("bpm", 80)),
        tuning=tuning,
        description=meta.get("description", ""),
        source=source,
        beats_per_note=beats_per_note,
        metadata=meta,
    )


def render_tab(exercise: Exercise, steps_per_line: int = 16) -> str:
    """Render as ASCII tab (with header) that parse_tab reads back identically."""
    header = [f"# title: {exercise.title}", f"# bpm: {exercise.bpm}"]
    if exercise.tuning != STANDARD_TUNING:
        header.append("# tuning: " + " ".join(midi_name(m) for m in exercise.tuning))
    if exercise.beats_per_note != 1:
        header.append(f"# beats-per-note: {exercise.beats_per_note:g}")
    if exercise.description:
        header.append(f"# description: {exercise.description}")
    names = _string_labels(exercise.tuning)
    systems = []
    for start in range(0, len(exercise.steps), steps_per_line):
        chunk = exercise.steps[start:start + steps_per_line]
        rows = []
        for string in reversed(range(len(exercise.tuning))):
            cells = []
            for step in chunk:
                fret = dict(step.notes).get(string)
                cells.append("---" if fret is None else f"{fret}".ljust(3, "-"))
            rows.append(f"{names[string]}|-" + "".join(cells) + "|")
        systems.append("\n".join(rows))
    return "\n".join(header) + "\n" + "\n\n".join(systems) + "\n"


def _string_labels(tuning: tuple[int, ...]) -> list[str]:
    if tuning == STANDARD_TUNING:
        return list(STRING_NAMES)
    labels = [midi_name(m)[:-1].rstrip("0123456789-") for m in tuning]
    width = max(len(label) for label in labels)
    return [label.ljust(width) for label in labels]


def load_tab_file(path: Path) -> Exercise:
    return parse_tab(path.read_text(encoding="utf-8"), source=str(path))


def bundled_dir() -> Path:
    return Path(__file__).parent / "exercises"


def user_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "guitar-app" / "songs"


def load_library(extra_dirs: list[Path] | None = None) -> tuple[list[Exercise], list[str]]:
    """Load every .tab file from the bundled and user folders. Returns (exercises, errors)."""
    exercises, errors = [], []
    for folder in [bundled_dir(), user_dir(), *(extra_dirs or [])]:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.tab")):
            try:
                exercises.append(load_tab_file(path))
            except (TabError, ValueError, KeyError) as error:
                errors.append(f"{path.name}: {error}")
    return exercises, errors

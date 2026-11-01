"""Generate practice exercises on the fly from scales, chords and finger patterns."""

from __future__ import annotations

import random

from .theory import (
    CHORDS, NOTE_NAMES, STANDARD_TUNING, FretPosition, chord_pitch_classes,
    parse_pitch_class, scale_pitch_classes,
)
from .tabs import Exercise, Step


def _root_pc(root: int | str) -> int:
    return parse_pitch_class(root) if isinstance(root, str) else root % 12


def root_position_fret(root: int | str, tuning: tuple[int, ...] = STANDARD_TUNING) -> int:
    """Fret of the root on the lowest string (0-11): where box 1 usually starts."""
    return (_root_pc(root) - tuning[0]) % 12


def box_positions(
    pitch_classes: tuple[int, ...],
    low_fret: int,
    span: int = 4,
    tuning: tuple[int, ...] = STANDARD_TUNING,
) -> list[FretPosition]:
    """Notes in one hand position (frets low_fret..low_fret+span), lowest pitch first.

    When two strings give the same pitch, the lower string wins, so the result is
    a clean run with each pitch once.
    """
    wanted = set(pitch_classes)
    by_midi: dict[int, FretPosition] = {}
    for string, open_midi in enumerate(tuning):
        for fret in range(low_fret, low_fret + span + 1):
            midi = open_midi + fret
            if midi % 12 in wanted and midi not in by_midi:
                by_midi[midi] = FretPosition(string, fret, midi)
    return [by_midi[m] for m in sorted(by_midi)]


def _exercise(title: str, positions: list[FretPosition], bpm: int, tuning, description: str) -> Exercise:
    steps = [Step(float(i), ((p.string, p.fret),)) for i, p in enumerate(positions)]
    return Exercise(title, steps, bpm=bpm, tuning=tuning, description=description, source="generated")


def scale_run(
    root: int | str,
    scale: str,
    *,
    low_fret: int | None = None,
    span: int = 4,
    group: int = 1,
    bpm: int = 70,
    tuning: tuple[int, ...] = STANDARD_TUNING,
) -> Exercise:
    """Up and back down a scale in one position.

    `group` > 1 plays the run in overlapping groups (group=3: 1-2-3, 2-3-4, ...),
    a standard way to build speed and fretboard knowledge.
    """
    root_pc = _root_pc(root)
    if low_fret is None:
        low_fret = max(0, root_position_fret(root_pc, tuning) - (1 if span > 3 else 0))
    notes = box_positions(scale_pitch_classes(root_pc, scale), low_fret, span, tuning)
    if len(notes) < 2:
        raise ValueError("position contains too few scale notes")
    up = _grouped(notes, group)
    down = _grouped(list(reversed(notes)), group)[1:]
    name = f"{NOTE_NAMES[root_pc]} {scale}"
    title = f"{name}, frets {low_fret}-{low_fret + span}" + (f", groups of {group}" if group > 1 else "")
    return _exercise(title, up + down, bpm, tuning, f"Play {name} up and down in one position.")


def _grouped(notes: list[FretPosition], group: int) -> list[FretPosition]:
    if group <= 1:
        return list(notes)
    out = []
    for start in range(len(notes) - group + 1):
        out.extend(notes[start:start + group])
    return out


def chromatic(
    start_fret: int = 1,
    fingers: tuple[int, ...] = (1, 2, 3, 4),
    *,
    bpm: int = 60,
    tuning: tuple[int, ...] = STANDARD_TUNING,
) -> Exercise:
    """Finger-independence drill: a finger order on every string, up then down."""
    up = [
        FretPosition(string, start_fret + f - 1, tuning[string] + start_fret + f - 1)
        for string in range(len(tuning))
        for f in fingers
    ]
    down = [
        FretPosition(string, start_fret + f - 1, tuning[string] + start_fret + f - 1)
        for string in reversed(range(len(tuning)))
        for f in reversed(fingers)
    ]
    order = "-".join(map(str, fingers))
    return _exercise(
        f"Chromatic {order} from fret {start_fret}", up + down, bpm, tuning,
        "One finger per fret. Keep fingers close to the strings.",
    )


def arpeggio(
    root: int | str,
    quality: str = "major",
    *,
    low_fret: int | None = None,
    span: int = 4,
    bpm: int = 70,
    tuning: tuple[int, ...] = STANDARD_TUNING,
) -> Exercise:
    root_pc = _root_pc(root)
    if quality not in CHORDS:
        raise ValueError(f"unknown chord quality {quality!r}")
    if low_fret is None:
        low_fret = max(0, root_position_fret(root_pc, tuning) - 1)
    notes = box_positions(chord_pitch_classes(root_pc, quality), low_fret, span, tuning)
    path = notes + list(reversed(notes))[1:]
    name = f"{NOTE_NAMES[root_pc]} {quality}"
    return _exercise(f"{name} arpeggio, frets {low_fret}-{low_fret + span}", path, bpm, tuning,
                     f"Chord tones of {name} only.")


def random_melody(
    root: int | str,
    scale: str,
    *,
    length: int = 16,
    max_leap: int = 2,
    low_fret: int | None = None,
    span: int = 4,
    bpm: int = 70,
    seed: int | None = None,
    tuning: tuple[int, ...] = STANDARD_TUNING,
) -> Exercise:
    """A new short melody each time: a random walk over the scale in one position.

    Steps move at most `max_leap` scale notes, so the result is playable and
    sounds like a line rather than noise. It starts and ends on the root when
    the position has one.
    """
    rng = random.Random(seed)
    root_pc = _root_pc(root)
    if low_fret is None:
        low_fret = max(0, root_position_fret(root_pc, tuning) - 1)
    notes = box_positions(scale_pitch_classes(root_pc, scale), low_fret, span, tuning)
    if len(notes) < 3:
        raise ValueError("position contains too few scale notes")
    roots = [i for i, n in enumerate(notes) if n.midi % 12 == root_pc]
    index = roots[0] if roots else len(notes) // 2
    path = [notes[index]]
    for _ in range(length - 2):
        options = [i for i in range(index - max_leap, index + max_leap + 1) if 0 <= i < len(notes) and i != index]
        index = rng.choice(options)
        path.append(notes[index])
    if roots:
        index = min(roots, key=lambda r: abs(r - index))
    path.append(notes[index])
    name = f"{NOTE_NAMES[root_pc]} {scale}"
    return _exercise(f"Random {name} melody", path, bpm, tuning,
                     f"Generated line in {name}. Read it, then play it in time.")


def note_finder(
    pitch_class: int | str,
    *,
    bpm: int = 50,
    tuning: tuple[int, ...] = STANDARD_TUNING,
) -> Exercise:
    """Find one note on every string, low to high: the classic fretboard memorisation drill."""
    pc = _root_pc(pitch_class)
    path = []
    for string, open_midi in enumerate(tuning):
        fret = (pc - open_midi) % 12
        path.append(FretPosition(string, fret, open_midi + fret))
    return _exercise(f"Find every {NOTE_NAMES[pc]}", path, bpm, tuning,
                     f"Play {NOTE_NAMES[pc]} on each string, low E to high e.")

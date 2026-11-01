from pathlib import Path
from types import SimpleNamespace

import guitarpro

from guitarapp import importers
from guitarapp.theory import STANDARD_TUNING

FIXTURES = Path(__file__).parent / "fixtures"


def gp_note(string, value, note_type="normal"):
    return SimpleNamespace(string=string, value=value, type=SimpleNamespace(name=note_type))


def gp_beat(start, duration, notes):
    return SimpleNamespace(
        start=start,
        duration=SimpleNamespace(time=duration * 960),
        notes=notes,
    )


def test_guitar_pro_import_maps_track_tuning_rhythm_and_skips_ties_and_rests(monkeypatch, tmp_path):
    strings = [SimpleNamespace(number=n, value=v) for n, v in zip(range(1, 7), (64, 59, 55, 50, 45, 38))]
    voice = SimpleNamespace(
        beats=[
            gp_beat(0, 1, [gp_note(6, 0)]),
            gp_beat(960, 0.5, [gp_note(5, 2)]),
            gp_beat(1440, 1, [gp_note(5, 2, "tie")]),
            gp_beat(2400, 1, []),
        ]
    )
    track = SimpleNamespace(
        name="Lead",
        isPercussionTrack=False,
        strings=strings,
        measures=[SimpleNamespace(start=0, voices=[voice])],
    )
    song = SimpleNamespace(title="Synthetic", artist="Tester", tempo=96, tracks=[track])
    monkeypatch.setattr(guitarpro, "parse", lambda _path: song)

    path = tmp_path / "synthetic.gp5"
    path.write_bytes(b"synthetic")
    exercises = importers.load_guitar_pro(path)

    exercise = exercises[0]
    assert exercise.tuning == (38, 45, 50, 55, 59, 64)
    assert [(step.beat, step.notes, step.duration) for step in exercise.steps] == [
        (0.0, ((0, 0),), 1.0),
        (1.0, ((1, 2),), 0.5),
    ]


def test_musicxml_import_uses_technical_positions_and_lowest_fret_fallback():
    exercises = importers.load_musicxml(FIXTURES / "simple.musicxml")

    exercise = exercises[0]
    assert exercise.tuning == STANDARD_TUNING
    assert [(step.beat, step.notes, step.duration) for step in exercise.steps] == [
        (0.0, ((4, 0), (5, 0)), 1.0),
        (1.5, ((5, 3),), 0.5),
        (4.0, ((4, 1),), 1.0),
    ]

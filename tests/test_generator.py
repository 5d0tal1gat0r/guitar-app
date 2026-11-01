import pytest

from guitarapp import generator as g
from guitarapp.theory import scale_pitch_classes


def midis(ex):
    return [m for s in ex.steps for m in ex.midi_notes(s)]


def test_scale_run_goes_up_then_down_in_key():
    ex = g.scale_run("A", "minor pentatonic")
    notes = midis(ex)
    top = notes.index(max(notes))
    assert notes[:top + 1] == sorted(notes[:top + 1])
    assert notes[top:] == sorted(notes[top:], reverse=True)
    assert notes[0] == notes[-1]
    assert {n % 12 for n in notes} <= set(scale_pitch_classes("A", "minor pentatonic"))
    frets = [f for s in ex.steps for _, f in s.notes]
    assert max(frets) - min(frets) <= 4  # one hand position


def test_groups_overlap():
    plain = midis(g.scale_run("C", "major", low_fret=7))
    grouped = midis(g.scale_run("C", "major", low_fret=7, group=3))
    assert grouped[:6] == [plain[0], plain[1], plain[2], plain[1], plain[2], plain[3]]


def test_random_melody_is_playable_and_reproducible():
    a = g.random_melody("D", "dorian", seed=3, length=24)
    b = g.random_melody("D", "dorian", seed=3, length=24)
    assert a.steps == b.steps
    assert len(a.steps) == 24
    notes = midis(a)
    assert notes[0] % 12 == 2 and notes[-1] % 12 == 2  # starts and ends on D
    assert {n % 12 for n in notes} <= set(scale_pitch_classes("D", "dorian"))


def test_chromatic_and_note_finder():
    ex = g.chromatic(start_fret=5)
    assert len(ex.steps) == 48
    finder = g.note_finder("G")
    assert {m % 12 for m in midis(finder)} == {7}
    assert len(finder.steps) == 6


def test_bad_arpeggio_quality():
    with pytest.raises(ValueError):
        g.arpeggio("C", "nonsense")

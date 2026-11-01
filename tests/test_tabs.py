import pytest

from guitarapp import generator
from guitarapp.tabs import TabError, load_library, parse_tab, render_tab
from guitarapp.theory import midi_name

WEB_TAB = """
Some intro text from a website
e|-------0-----|-----------|
B|-----1---1---|---3h5-----|
G|---0-------0-|-------7b--|
D|-2-----------|-----------|
A|-------------|-x---------|
E|-------------|-----------|

e|--12--------|
B|------------|
G|------------|
D|------------|
A|------------|
E|---------0--|
"""


def test_parses_web_style_tab():
    ex = parse_tab(WEB_TAB)
    notes = [midi_name(m) for s in ex.steps for m in ex.midi_notes(s)]
    assert notes == ["E3", "G3", "C4", "E4", "C4", "G3", "D4", "E4", "D4", "E5", "E2"]
    assert [s.beat for s in ex.steps] == list(range(11))


def test_chords_share_a_step():
    ex = parse_tab("e|-0-|\nB|-1-|\nG|-0-|\nD|-2-|\nA|-3-|\nE|---|\n")
    assert len(ex.steps) == 1
    assert sorted(midi_name(m) for m in ex.midi_notes(ex.steps[0])) == ["C3", "C4", "E3", "E4", "G3"]


def test_header_metadata():
    ex = parse_tab("# title: Drop D riff\n# bpm: 100\n# tuning: D2 A2 D3 G3 B3 E4\n# beats-per-note: 0.5\n"
                   "e|---|\nB|---|\nG|---|\nD|---|\nA|---|\nD|-0-2-|\n")
    assert ex.title == "Drop D riff" and ex.bpm == 100
    assert [midi_name(m) for s in ex.steps for m in ex.midi_notes(s)] == ["D2", "E2"]
    assert ex.steps[1].beat == 0.5


def test_errors():
    with pytest.raises(TabError):
        parse_tab("no tab here")
    with pytest.raises(TabError):
        parse_tab("e|-0-|\nB|-1-|\n")


@pytest.mark.parametrize("make", [
    lambda: generator.scale_run("A", "minor pentatonic"),
    lambda: generator.scale_run("G", "major", group=3),
    lambda: generator.random_melody("E", "natural minor", seed=7, length=40),
    lambda: generator.chromatic(),
    lambda: generator.arpeggio("C", "major 7"),
    lambda: generator.note_finder("F#"),
])
def test_render_parse_round_trip(make):
    ex = make()
    back = parse_tab(render_tab(ex))
    assert back.steps == ex.steps
    assert back.title == ex.title and back.bpm == ex.bpm


def test_bundled_library_loads():
    exercises, errors = load_library()
    assert errors == []
    assert len(exercises) >= 6

import pytest

from guitarapp import theory as t


def test_note_parsing_and_names():
    assert t.parse_note("E2") == 40
    assert t.parse_note("A4") == 69
    assert t.parse_note("Bb3") == t.parse_note("A#3") == 58
    assert t.midi_name(40) == "E2"
    assert [t.midi_name(m) for m in t.STANDARD_TUNING] == ["E2", "A2", "D3", "G3", "B3", "E4"]
    with pytest.raises(ValueError):
        t.parse_note("H2")


def test_frequency_conversion():
    assert t.midi_to_freq(69) == pytest.approx(440.0)
    assert t.midi_to_freq(40) == pytest.approx(82.4069, abs=1e-3)
    assert t.freq_to_midi(t.midi_to_freq(52)) == pytest.approx(52)
    assert t.cents_from_midi(440.0 * 2 ** (10 / 1200), 69) == pytest.approx(10)


def test_scales_and_chords():
    assert t.scale_pitch_classes("C", "major") == (0, 2, 4, 5, 7, 9, 11)
    assert t.scale_pitch_classes("A", "minor pentatonic") == (9, 0, 2, 4, 7)
    assert t.chord_pitch_classes("G", "dominant 7") == (7, 11, 2, 5)
    assert [c.name for c in t.diatonic_triads("C")] == ["C", "Dm", "Em", "F", "G", "Am", "Bdim"]
    assert [c.name for c in t.diatonic_triads("A", "natural minor")] == ["Am", "Bdim", "C", "Dm", "Em", "F", "G"]
    assert t.interval_name(7) == "perfect 5th"


def test_fretboard_lookup():
    places = t.fret_for_midi(t.parse_note("E4"))
    assert (5, 0) in [(p.string, p.fret) for p in places]
    assert (4, 5) in [(p.string, p.fret) for p in places]
    roots = [p for p in t.fret_positions({9}, max_fret=12) if p.string == 0]
    assert [p.fret for p in roots] == [5]


def test_render_fretboard_marks_root():
    diagram = t.render_fretboard("A", "minor pentatonic", max_fret=5)
    low_e = diagram.splitlines()[-1]
    assert low_e.startswith("E|")
    assert low_e[2 + 5 * 4] == "R"  # fret 5 on low E is A

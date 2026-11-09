from guitarapp.pitch import NoteReading
from guitarapp.practice import PracticeSession, Verdict
from guitarapp.tabs import parse_tab

# A2, B2, C3, D3 on the A string, at 60 BPM: one note per second.
EXERCISE = parse_tab("# bpm: 60\ne|---------|\nB|---------|\nG|---------|\nD|---------|\nA|-0-2-3-5-|\nE|---------|\n")


def note(midi, cents=0.0):
    return NoteReading(midi, cents, 0.0)


def test_verdicts():
    s = PracticeSession(EXERCISE, start_time=10.0, tolerance_cents=25)
    assert s.on_note(9.0, note(45)) is None  # before the first window
    assert s.on_note(10.05, note(45)).verdict is Verdict.CORRECT
    assert s.on_note(11.1, note(48)).verdict is Verdict.WRONG
    assert s.on_note(12.0, note(48, cents=40)).verdict is Verdict.OUT_OF_TUNE
    s.advance(14.5)  # D3 never played
    assert s.finished
    assert [r.verdict for r in s.results] == [Verdict.CORRECT, Verdict.WRONG, Verdict.OUT_OF_TUNE, Verdict.MISSED]
    summary = s.summary()
    assert (summary.correct, summary.wrong, summary.out_of_tune, summary.missed) == (1, 1, 1, 1)
    assert summary.accuracy == 0.25


def test_first_note_in_window_decides():
    s = PracticeSession(EXERCISE, start_time=0.0)
    s.on_note(0.1, note(46))
    assert s.on_note(0.3, note(45)) is None
    s.advance(1.0)
    assert s.results[0].verdict is Verdict.WRONG


def test_early_pluck_counts_and_timing_is_measured():
    s = PracticeSession(EXERCISE, start_time=0.0, early_ms=120)
    result = s.on_note(0.9, note(47))  # 100 ms before step 2's beat
    assert result.index == 1 and result.verdict is Verdict.CORRECT
    assert round(result.timing_ms) == -100


def test_tempo_override_and_octave_option():
    s = PracticeSession(EXERCISE, start_time=0.0, bpm=120, ignore_octave=True)
    assert s.step_start(2) == 1.0
    assert s.on_note(0.0, note(57)).verdict is Verdict.CORRECT  # A3 for A2


def test_windows_follow_next_step_and_last_duration():
    exercise = parse_tab(
        "# bpm: 60\n# durations: 0.5 1.5 0.25\n"
        "e|-0---2-------3-|\nB|----------------|\nG|----------------|\n"
        "D|----------------|\nA|----------------|\nE|----------------|\n"
    )
    session = PracticeSession(exercise, start_time=0.0)

    assert session.step_end(0) == 0.5
    assert session.step_end(1) == 2.0
    assert session.step_end(2) == 2.25

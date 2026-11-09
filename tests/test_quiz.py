import random

import numpy as np

from guitarapp.pitch import NoteReading, detect_pitch, reading_from_freq
from guitarapp.quiz import (
    ALL_INTERVALS, Score, interval_audio, interval_question, is_right_name, is_right_played,
    note_question, pluck,
)
from guitarapp.theory import parse_note


def test_note_questions_stay_in_range_and_change():
    rng = random.Random(4)
    previous = None
    for _ in range(200):
        q = note_question(rng, max_fret=5, previous=previous)
        assert 0 <= q.fret <= 5 and 0 <= q.string <= 5
        assert q != previous
        previous = q


def test_answer_checks():
    q = note_question(random.Random(0))
    assert is_right_name(q, q.midi % 12)
    assert not is_right_name(q, q.midi + 1)
    assert is_right_played(q, NoteReading(q.midi, 5.0, 0.0))
    assert not is_right_played(q, NoteReading(q.midi + 12, 0.0, 0.0))  # wrong octave = wrong place


def test_interval_questions():
    rng = random.Random(1)
    qs = [interval_question(rng, ALL_INTERVALS) for _ in range(300)]
    assert {q.semitones for q in qs} == set(ALL_INTERVALS)
    assert interval_question(random.Random(0), (7,)).answer == "perfect 5th"
    assert interval_question(random.Random(0), (12,)).answer == "octave"


def test_score():
    s = Score()
    for answer in (True, True, False, True):
        s.record(answer)
    assert (s.asked, s.right, s.streak, s.best_streak) == (4, 3, 1, 2)


def test_synth_plays_the_right_pitch():
    tone = pluck(parse_note("A2"))
    pitch = detect_pitch(tone[4410:4410 + 2048], 44100)
    assert reading_from_freq(pitch.freq).midi == parse_note("A2")


def test_interval_audio_lengths():
    q = interval_question(random.Random(2))
    assert len(interval_audio(q)) > len(interval_audio(q, harmonic=True))
    assert np.max(np.abs(interval_audio(q, harmonic=True))) <= 1.0

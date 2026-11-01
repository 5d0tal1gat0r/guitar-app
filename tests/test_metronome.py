import numpy as np
import pytest

from guitarapp.metronome import MetronomeClock, TapTempo, click
from guitarapp.pitch import detect_pitch


def beat_times(clock, blocks, block=256):
    found, position = [], 0
    for _ in range(blocks):
        audio, beats = clock.render(block)
        assert len(audio) == block
        found += [(beat, position + offset) for beat, offset in beats]
        position += block
    return found


def test_beats_are_sample_exact():
    clock = MetronomeClock(44100, bpm=120, beats_per_bar=4)
    beats = beat_times(clock, 1000)
    assert beats[:5] == [(0, 0), (1, 22050), (2, 44100), (3, 66150), (0, 88200)]


def test_no_drift_with_fractional_interval():
    clock = MetronomeClock(44100, bpm=97, beats_per_bar=3)
    beats = beat_times(clock, 20000, block=137)
    spb = 44100 * 60 / 97
    for index, (beat, sample) in enumerate(beats):
        assert beat == index % 3
        assert abs(sample - index * spb) <= 0.5


def test_subdivisions_click_between_beats():
    clock = MetronomeClock(44100, bpm=60, beats_per_bar=4, subdivision=2)
    audio = np.concatenate([clock.render(441)[0] for _ in range(200)])  # 2 s
    onsets = np.flatnonzero(np.abs(audio) > 0.05)
    assert onsets[0] < 20
    assert np.any((onsets > 22050) & (onsets < 22100))  # the "and" of beat 1


def test_tempo_is_clamped():
    clock = MetronomeClock(bpm=5)
    assert clock.bpm == 20
    clock.bpm = 999
    assert clock.bpm == 300


def test_click_is_not_heard_as_a_note():
    for accent in (True, False):
        frame = np.zeros(2048)
        sound = click(44100, accent)
        frame[300:300 + len(sound)] = sound
        assert detect_pitch(frame, 44100) is None


def test_tap_tempo():
    tap = TapTempo()
    assert tap.tap(0.0) is None
    for i in range(1, 5):
        bpm = tap.tap(i * 0.5)
    assert bpm == pytest.approx(120)
    assert tap.tap(10.0) is None  # long pause starts over

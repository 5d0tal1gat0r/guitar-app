import numpy as np
import pytest

from guitarapp.pitch import NoteTracker, Pitch, detect_pitch, reading_from_freq
from guitarapp.theory import midi_to_freq

SR = 44100


def guitar_like(freq, n=2048, sr=SR, noise=0.0, seed=0):
    """Plucked-string stand-in: strong 2nd harmonic (fools naive detectors), decay, noise."""
    t = np.arange(n) / sr
    tone = 0.3 * np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * 2 * freq * t + 0.3)
    tone += 0.2 * np.sin(2 * np.pi * 3 * freq * t + 1.1) + 0.1 * np.sin(2 * np.pi * 4 * freq * t)
    tone *= np.exp(-t * 3)
    if noise:
        tone += np.random.default_rng(seed).normal(0, noise, n)
    return tone


@pytest.mark.parametrize("midi", range(40, 84))  # low E to B5, every note
def test_detects_every_guitar_note(midi):
    freq = midi_to_freq(midi)
    pitch = detect_pitch(guitar_like(freq, noise=0.02), SR, fmax=1050)
    assert pitch is not None
    assert reading_from_freq(pitch.freq).midi == midi
    assert abs(reading_from_freq(pitch.freq).cents) < 3


def test_silence_and_noise_give_none():
    assert detect_pitch(np.zeros(2048), SR) is None
    noise = np.random.default_rng(1).uniform(-0.5, 0.5, 2048)
    assert detect_pitch(noise, SR) is None


def test_detuned_note_reports_cents():
    freq = midi_to_freq(45) * 2 ** (20 / 1200)  # A2, 20 cents sharp
    reading = reading_from_freq(detect_pitch(guitar_like(freq), SR).freq)
    assert reading.midi == 45
    assert reading.cents == pytest.approx(20, abs=2)


def test_frame_too_short_raises():
    with pytest.raises(ValueError):
        detect_pitch(guitar_like(110, n=512), SR)


def test_tracker_reports_each_note_once():
    tracker = NoteTracker(frames_to_confirm=3)
    a = Pitch(110.0, 0.9)
    out = [tracker.update(a, 0.1) for _ in range(6)]
    assert [r.midi for r in out if r] == [45]
    b = Pitch(midi_to_freq(47), 0.9)
    out = [tracker.update(b, 0.1) for _ in range(4)]
    assert [r.midi for r in out if r] == [47]


def test_tracker_needs_agreement():
    tracker = NoteTracker(frames_to_confirm=3)
    for freq in (110.0, 123.5, 110.0, 123.5):
        assert tracker.update(Pitch(freq, 0.9), 0.1) is None


def test_repluck_same_note_is_reported_again():
    tracker = NoteTracker(frames_to_confirm=2)
    a = Pitch(110.0, 0.9)
    first = [tracker.update(a, level) for level in (0.2, 0.15, 0.1, 0.08)]
    second = [tracker.update(a, level) for level in (0.3, 0.25)]  # loudness jump: new pluck
    assert sum(r is not None for r in first) == 1
    assert sum(r is not None for r in second) == 1

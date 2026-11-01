"""Monophonic pitch detection (YIN) and note stabilisation for live mic input."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from .theory import A4_HZ, cents_from_midi, freq_to_midi


@dataclass(frozen=True)
class Pitch:
    freq: float
    confidence: float  # 0-1, 1 = perfectly periodic


def rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def detect_pitch(
    samples: np.ndarray,
    sample_rate: int,
    *,
    fmin: float = 70.0,
    fmax: float = 1200.0,
    threshold: float = 0.15,
    min_rms: float = 0.005,
) -> Pitch | None:
    """Estimate the fundamental frequency of `samples` with the YIN algorithm.

    Returns None for silence or when no clear period is found. The frame must
    hold at least two periods of `fmin` (2048 samples at 44.1 kHz covers 70 Hz).
    """
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim != 1:
        raise ValueError("expected mono samples")
    if rms(x) < min_rms:
        return None
    tau_min = max(2, int(sample_rate / fmax))
    tau_max = int(sample_rate / fmin)
    window = len(x) - tau_max
    if window < tau_max:
        raise ValueError(f"frame too short for fmin={fmin} Hz: need {2 * tau_max} samples")

    x = x - x.mean()
    head = x[:window]
    diff = np.empty(tau_max + 1)
    diff[0] = 0.0
    for tau in range(1, tau_max + 1):
        delta = head - x[tau:tau + window]
        diff[tau] = np.dot(delta, delta)

    # Cumulative mean normalised difference.
    cmnd = np.ones_like(diff)
    running = np.cumsum(diff[1:])
    with np.errstate(divide="ignore", invalid="ignore"):
        cmnd[1:] = np.where(running > 0, diff[1:] * np.arange(1, tau_max + 1) / running, 1.0)

    tau = _first_dip(cmnd, tau_min, tau_max, threshold)
    if tau is None:
        return None
    refined = _parabolic(cmnd, tau)
    return Pitch(sample_rate / refined, float(max(0.0, 1.0 - cmnd[tau])))


def _first_dip(cmnd: np.ndarray, tau_min: int, tau_max: int, threshold: float) -> int | None:
    tau = tau_min
    while tau < tau_max:
        if cmnd[tau] < threshold:
            while tau + 1 < tau_max and cmnd[tau + 1] < cmnd[tau]:
                tau += 1
            return tau
        tau += 1
    return None


def _parabolic(values: np.ndarray, index: int) -> float:
    if index <= 0 or index >= len(values) - 1:
        return float(index)
    left, centre, right = values[index - 1], values[index], values[index + 1]
    denom = left - 2 * centre + right
    if denom == 0:
        return float(index)
    return index + 0.5 * (left - right) / denom


@dataclass(frozen=True)
class NoteReading:
    midi: int
    cents: float  # offset from the equal-tempered note, + = sharp
    freq: float


def reading_from_freq(freq: float, a4_hz: float = A4_HZ) -> NoteReading:
    midi = round(freq_to_midi(freq, a4_hz))
    return NoteReading(midi, cents_from_midi(freq, midi, a4_hz), freq)


class NoteTracker:
    """Turns noisy per-frame pitches into stable notes.

    A note counts once it is the same for `frames_to_confirm` frames in a row;
    `update` returns it only on the frame it becomes stable, so each pluck is
    reported once. Silence resets the tracker, and so does a jump in loudness
    (a new pluck), so a repeated note is reported again.
    """

    def __init__(self, frames_to_confirm: int = 3, a4_hz: float = A4_HZ, onset_ratio: float = 1.6):
        self.frames_to_confirm = frames_to_confirm
        self.a4_hz = a4_hz
        self.onset_ratio = onset_ratio
        self._recent: deque[NoteReading] = deque(maxlen=frames_to_confirm)
        self._level = 0.0
        self.current: NoteReading | None = None

    def update(self, pitch: Pitch | None, level: float | None = None) -> NoteReading | None:
        """Feed one analysis frame. `level` is the frame's RMS, used to spot new plucks."""
        if level is not None:
            onset = self._level > 0 and level > self._level * self.onset_ratio
            self._level = level
            if onset:
                self._recent.clear()
                self.current = None
        if pitch is None:
            self._recent.clear()
            self.current = None
            return None
        reading = reading_from_freq(pitch.freq, self.a4_hz)
        self._recent.append(reading)
        if len(self._recent) < self.frames_to_confirm:
            return None
        if any(r.midi != reading.midi for r in self._recent):
            return None
        averaged = NoteReading(
            reading.midi,
            float(np.mean([r.cents for r in self._recent])),
            float(np.mean([r.freq for r in self._recent])),
        )
        is_new = self.current is None or self.current.midi != reading.midi
        self.current = averaged
        return averaged if is_new else None

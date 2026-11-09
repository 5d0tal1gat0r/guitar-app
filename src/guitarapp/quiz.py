"""Fretboard-note and interval ear-training quizzes (pure logic) plus a plucked-string synth."""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np

from .pitch import NoteReading
from .theory import STANDARD_TUNING, interval_name, midi_to_freq

# Intervals offered in ear training, by difficulty.
BASIC_INTERVALS = (3, 4, 5, 7, 12)
ALL_INTERVALS = tuple(range(1, 13))


@dataclass(frozen=True)
class NoteQuestion:
    string: int  # 0 = low E
    fret: int
    midi: int


def note_question(rng: random.Random, max_fret: int = 12,
                  tuning: tuple[int, ...] = STANDARD_TUNING,
                  previous: NoteQuestion | None = None) -> NoteQuestion:
    """A random fretboard position, never the same as the previous one."""
    while True:
        string = rng.randrange(len(tuning))
        fret = rng.randint(0, max_fret)
        question = NoteQuestion(string, fret, tuning[string] + fret)
        if question != previous:
            return question


def is_right_name(question: NoteQuestion, pitch_class: int) -> bool:
    return question.midi % 12 == pitch_class % 12


def is_right_played(question: NoteQuestion, reading: NoteReading) -> bool:
    """Playing must hit the exact pitch (same octave), so the right fret is needed, not just the name."""
    return reading.midi == question.midi


@dataclass(frozen=True)
class IntervalQuestion:
    low: int  # MIDI
    semitones: int

    @property
    def high(self) -> int:
        return self.low + self.semitones

    @property
    def answer(self) -> str:
        return "octave" if self.semitones == 12 else interval_name(self.semitones)


def interval_question(rng: random.Random, allowed: tuple[int, ...] = BASIC_INTERVALS,
                      low_range: tuple[int, int] = (45, 64)) -> IntervalQuestion:
    return IntervalQuestion(rng.randint(*low_range), rng.choice(allowed))


@dataclass
class Score:
    asked: int = 0
    right: int = 0
    streak: int = 0
    best_streak: int = 0

    def record(self, correct: bool) -> None:
        self.asked += 1
        if correct:
            self.right += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
        else:
            self.streak = 0

    def __str__(self) -> str:
        if not self.asked:
            return "No answers yet"
        return f"{self.right}/{self.asked} right ({self.right / self.asked:.0%}), streak {self.streak}, best {self.best_streak}"


def pluck(midi: int, sample_rate: int = 44100, duration: float = 1.2, seed: int = 0) -> np.ndarray:
    """Karplus-Strong plucked string: sounds close to a guitar, cheap to compute."""
    freq = midi_to_freq(midi)
    period = int(round(sample_rate / freq))
    buffer = np.random.default_rng(seed).uniform(-1, 1, period)
    out = np.empty(int(sample_rate * duration))
    for i in range(len(out)):
        out[i] = buffer[i % period]
        buffer[i % period] = 0.996 * 0.5 * (buffer[i % period] + buffer[(i + 1) % period])
    fade = np.minimum(1.0, np.linspace(0, duration, len(out))[::-1] / 0.05)  # no click at the end
    return (0.5 * out * fade).astype(np.float32)


def interval_audio(question: IntervalQuestion, sample_rate: int = 44100, harmonic: bool = False) -> np.ndarray:
    """Melodic: low note then high note. Harmonic: both together."""
    low, high = pluck(question.low, sample_rate, seed=1), pluck(question.high, sample_rate, seed=2)
    if harmonic:
        return (0.7 * (low + high)).astype(np.float32)
    gap = int(0.75 * sample_rate)
    out = np.zeros(gap + len(high), dtype=np.float32)
    out[:len(low)] += low
    out[gap:] += high
    return out

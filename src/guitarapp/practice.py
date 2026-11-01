"""Practice session: compare what the player plays with what the exercise expects.

Time is passed in by the caller (seconds on any monotonic clock), so the
logic runs the same live and in tests.

Each step owns a time window of its length in beats. The first stable note
heard inside the window decides the verdict:

- correct: right note, within `tolerance_cents`
- out_of_tune: right note name, but further off than the tolerance
- wrong: a different note
- missed: nothing stable heard in the window

Detection is monophonic: for a chord step, playing any one of its notes counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .pitch import NoteReading
from .tabs import Exercise, Step


class Verdict(str, Enum):
    CORRECT = "correct"
    OUT_OF_TUNE = "out_of_tune"
    WRONG = "wrong"
    MISSED = "missed"


@dataclass
class StepResult:
    index: int
    step: Step
    expected: tuple[int, ...]
    verdict: Verdict
    played: NoteReading | None = None
    timing_ms: float | None = None  # + = late, relative to the step's start


@dataclass
class Summary:
    total: int
    correct: int
    out_of_tune: int
    wrong: int
    missed: int
    mean_abs_timing_ms: float | None

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def judge(expected: tuple[int, ...], reading: NoteReading, tolerance_cents: float,
          ignore_octave: bool = False) -> Verdict:
    def same(a: int, b: int) -> bool:
        return a % 12 == b % 12 if ignore_octave else a == b

    if any(same(reading.midi, midi) for midi in expected):
        return Verdict.CORRECT if abs(reading.cents) <= tolerance_cents else Verdict.OUT_OF_TUNE
    return Verdict.WRONG


class PracticeSession:
    def __init__(
        self,
        exercise: Exercise,
        start_time: float,
        *,
        bpm: float | None = None,
        tolerance_cents: float = 30.0,
        ignore_octave: bool = False,
        early_ms: float = 120.0,
    ):
        self.exercise = exercise
        self.start_time = start_time
        self.bpm = bpm or exercise.bpm
        self.tolerance_cents = tolerance_cents
        self.ignore_octave = ignore_octave
        # The window opens slightly before the beat so a pluck just ahead of it counts.
        self.early = early_ms / 1000.0
        self.results: list[StepResult] = []
        self._pending: StepResult | None = None

    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.bpm

    def step_start(self, index: int) -> float:
        return self.start_time + self.exercise.steps[index].beat * self.seconds_per_beat

    def step_end(self, index: int) -> float:
        return self.step_start(index) + self.exercise.beats_per_note * self.seconds_per_beat

    @property
    def finished(self) -> bool:
        return len(self.results) == len(self.exercise.steps)

    def current_index(self, now: float) -> int | None:
        """Index of the step whose window contains `now` (None before start or after end)."""
        index = len(self.results)
        if index >= len(self.exercise.steps) or now < self.step_start(index) - self.early:
            return None
        return index

    def on_note(self, now: float, reading: NoteReading) -> StepResult | None:
        """Feed a newly stable note. Returns the result if it decided a step."""
        self.advance(now)
        index = self.current_index(now)
        if index is None or self._pending is not None:
            return None
        step = self.exercise.steps[index]
        expected = self.exercise.midi_notes(step)
        verdict = judge(expected, reading, self.tolerance_cents, self.ignore_octave)
        self._pending = StepResult(index, step, expected, verdict, reading,
                                   (now - self.step_start(index)) * 1000.0)
        return self._pending

    def advance(self, now: float) -> list[StepResult]:
        """Close every step whose window has ended. Returns the newly closed results."""
        closed = []
        while not self.finished and now >= self.step_end(len(self.results)) - self.early:
            index = len(self.results)
            result = self._pending
            if result is None:
                step = self.exercise.steps[index]
                result = StepResult(index, step, self.exercise.midi_notes(step), Verdict.MISSED)
            self._pending = None
            self.results.append(result)
            closed.append(result)
        return closed

    def summary(self) -> Summary:
        counts = {v: sum(1 for r in self.results if r.verdict is v) for v in Verdict}
        timings = [abs(r.timing_ms) for r in self.results if r.timing_ms is not None]
        return Summary(
            total=len(self.results),
            correct=counts[Verdict.CORRECT],
            out_of_tune=counts[Verdict.OUT_OF_TUNE],
            wrong=counts[Verdict.WRONG],
            missed=counts[Verdict.MISSED],
            mean_abs_timing_ms=sum(timings) / len(timings) if timings else None,
        )

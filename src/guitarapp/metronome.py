"""Sample-accurate metronome.

Clicks are mixed into the audio stream by sample position, not by timers, so
tempo stays exact regardless of GUI load. `MetronomeClock.render` is pure and
testable; `Metronome` wraps it in a sounddevice output stream.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import numpy as np

MIN_BPM = 20
MAX_BPM = 300


def click(sample_rate: int, accent: bool) -> np.ndarray:
    """Short decaying noise burst, like a wood block.

    Noise rather than a tone, so the pitch detector never mistakes the click
    for a played note when the mic hears the speakers.
    """
    duration = 0.025
    n = int(sample_rate * duration)
    t = np.arange(n) / sample_rate
    noise = np.random.default_rng(1 if accent else 2).uniform(-1.0, 1.0, n)
    if not accent:
        noise = np.convolve(noise, np.ones(4) / 4, mode="same")  # darker
    amplitude = 0.9 if accent else 0.6
    return (amplitude * noise * np.exp(-t * 250)).astype(np.float32)


class MetronomeClock:
    """Produces click audio block by block and reports which beats fall in each block."""

    def __init__(self, sample_rate: int = 44100, bpm: float = 80, beats_per_bar: int = 4, subdivision: int = 1):
        self.sample_rate = sample_rate
        self.bpm = bpm
        self.beats_per_bar = beats_per_bar
        self.subdivision = subdivision  # clicks per beat: 1 quarter, 2 eighths, 3 triplets, 4 sixteenths
        self._accent = click(sample_rate, accent=True)
        self._normal = click(sample_rate, accent=False)
        self._sub = self._normal * 0.4
        self.reset()

    def reset(self) -> None:
        self._position = 0  # samples rendered so far
        self._next_tick = 0.0  # sample index of the next click
        self._tick_index = 0
        self._tail = np.zeros(0, dtype=np.float32)  # click audio spilling into the next block

    @property
    def bpm(self) -> float:
        return self._bpm

    @bpm.setter
    def bpm(self, value: float) -> None:
        self._bpm = float(min(MAX_BPM, max(MIN_BPM, value)))

    def samples_per_tick(self) -> float:
        return self.sample_rate * 60.0 / self._bpm / self.subdivision

    def render(self, frames: int) -> tuple[np.ndarray, list[tuple[int, int]]]:
        """Return `frames` samples of audio and the (beat_in_bar, offset) of each beat started."""
        out = np.zeros(frames, dtype=np.float32)
        carried = min(frames, len(self._tail))
        out[:carried] += self._tail[:carried]
        self._tail = self._tail[carried:]

        beats = []
        end = self._position + frames
        while self._next_tick < end:
            offset = int(round(self._next_tick)) - self._position
            offset = min(max(offset, 0), frames - 1)
            sound = self._sound_for(self._tick_index)
            if self._tick_index % self.subdivision == 0:
                beat = (self._tick_index // self.subdivision) % self.beats_per_bar
                beats.append((beat, offset))
            self._mix(out, sound, offset)
            self._tick_index += 1
            self._next_tick += self.samples_per_tick()
        self._position = end
        return out, beats

    def _sound_for(self, tick: int) -> np.ndarray:
        if tick % self.subdivision:
            return self._sub
        beat = (tick // self.subdivision) % self.beats_per_bar
        return self._accent if beat == 0 else self._normal

    def _mix(self, out: np.ndarray, sound: np.ndarray, offset: int) -> None:
        fits = min(len(sound), len(out) - offset)
        out[offset:offset + fits] += sound[:fits]
        spill = sound[fits:]
        if len(spill):
            if len(self._tail) < len(spill):
                self._tail = np.pad(self._tail, (0, len(spill) - len(self._tail)))
            self._tail[:len(spill)] += spill


class TapTempo:
    """Average the interval between recent taps; a pause over 2 s starts over."""

    def __init__(self, max_taps: int = 6):
        self.max_taps = max_taps
        self._taps: list[float] = []

    def tap(self, now: float) -> float | None:
        if self._taps and now - self._taps[-1] > 2.0:
            self._taps.clear()
        self._taps = (self._taps + [now])[-self.max_taps:]
        if len(self._taps) < 2:
            return None
        intervals = np.diff(self._taps)
        return float(min(MAX_BPM, max(MIN_BPM, 60.0 / np.mean(intervals))))


class Metronome:
    """Plays a MetronomeClock through the default audio output."""

    def __init__(self, sample_rate: int = 44100, on_beat: Callable[[int], None] | None = None):
        self.clock = MetronomeClock(sample_rate)
        self.on_beat = on_beat  # called from the audio thread; keep it cheap
        self._stream = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        if self._stream is not None:
            return
        with self._lock:
            self.clock.reset()
        self._stream = sd.OutputStream(
            samplerate=self.clock.sample_rate, channels=1, dtype="float32",
            blocksize=256, latency="low", callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def output_latency(self) -> float:
        """Seconds between rendering a click and hearing it."""
        return float(self._stream.latency) if self._stream is not None else 0.0

    def _callback(self, outdata, frames, _time, _status) -> None:
        with self._lock:
            audio, beats = self.clock.render(frames)
        outdata[:, 0] = audio
        if self.on_beat:
            for beat, _offset in beats:
                self.on_beat(beat)

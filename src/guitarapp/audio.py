"""Microphone capture into a rolling buffer that the GUI analyses on a timer."""

from __future__ import annotations

import threading

import numpy as np


class RollingBuffer:
    """Keeps the most recent `size` mono samples. Thread-safe."""

    def __init__(self, size: int):
        self._data = np.zeros(size, dtype=np.float32)
        self._lock = threading.Lock()
        self.total_written = 0

    def write(self, samples: np.ndarray) -> None:
        samples = np.asarray(samples, dtype=np.float32)[-len(self._data):]
        n = len(samples)
        with self._lock:
            self._data = np.roll(self._data, -n)
            self._data[-n:] = samples
            self.total_written += n

    def latest(self) -> np.ndarray:
        with self._lock:
            return self._data.copy()


class MicInput:
    """Default (or chosen) input device -> RollingBuffer of `frame_size` samples."""

    def __init__(self, sample_rate: int = 44100, frame_size: int = 2048, device: int | str | None = None):
        self.sample_rate = sample_rate
        self.device = device
        self.buffer = RollingBuffer(frame_size)
        self._stream = None

    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate, channels=1, dtype="float32",
            blocksize=512, device=self.device, callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata, _frames, _time, _status) -> None:
        self.buffer.write(indata[:, 0])


def input_devices() -> list[tuple[int, str]]:
    """(index, name) of every device that can record."""
    import sounddevice as sd

    return [
        (index, device["name"])
        for index, device in enumerate(sd.query_devices())
        if device["max_input_channels"] > 0
    ]

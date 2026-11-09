"""Practice history: every finished session, stored as JSON in the XDG data folder."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

# A run at or above this accuracy counts as "clean" for the tempo record.
CLEAN_ACCURACY = 0.9


@dataclass(frozen=True)
class SessionRecord:
    title: str
    when: str  # ISO timestamp, local time
    bpm: float
    total: int
    correct: int
    mean_abs_timing_ms: float | None = None

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def day(self) -> date:
        return datetime.fromisoformat(self.when).date()


@dataclass(frozen=True)
class ExerciseStats:
    title: str
    sessions: int
    best_accuracy: float
    best_clean_bpm: float | None  # fastest run with accuracy >= CLEAN_ACCURACY
    last_played: str


def _validated(record: SessionRecord) -> SessionRecord:
    """Reject records that would crash later (bad dates, impossible counts)."""
    datetime.fromisoformat(record.when)
    if not isinstance(record.title, str):
        raise TypeError("title must be text")
    if not (isinstance(record.total, int) and isinstance(record.correct, int) and 0 <= record.correct <= record.total):
        raise ValueError("correct/total out of range")
    if not (isinstance(record.bpm, (int, float)) and record.bpm > 0):
        raise ValueError("bpm must be positive")
    return record


def default_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "guitar-app" / "history.json"


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self.records: list[SessionRecord] = self._load()

    def _load(self) -> list[SessionRecord]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return [_validated(SessionRecord(**item)) for item in raw]
        except FileNotFoundError:
            return []
        except (ValueError, TypeError, AttributeError):
            # Keep a broken file for the user instead of overwriting it.
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            self.path.rename(self.path.with_name(f"{self.path.stem}.corrupt-{stamp}.json"))
            return []

    def add(self, record: SessionRecord) -> None:
        self.records.append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(r) for r in self.records], indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def stats(self, title: str) -> ExerciseStats | None:
        runs = [r for r in self.records if r.title == title]
        if not runs:
            return None
        clean = [r.bpm for r in runs if r.accuracy >= CLEAN_ACCURACY]
        return ExerciseStats(
            title=title,
            sessions=len(runs),
            best_accuracy=max(r.accuracy for r in runs),
            best_clean_bpm=max(clean) if clean else None,
            last_played=max(r.when for r in runs),
        )

    def all_stats(self) -> list[ExerciseStats]:
        """One row per exercise, most recently played first."""
        titles = {r.title for r in self.records}
        rows = [s for s in (self.stats(t) for t in titles) if s]
        return sorted(rows, key=lambda s: s.last_played, reverse=True)

    def streak(self, today: date | None = None) -> int:
        """Consecutive days with practice, ending today (or yesterday, so it survives until you play)."""
        days = {r.day for r in self.records}
        day = today or date.today()
        if day not in days:
            day -= timedelta(days=1)
        count = 0
        while day in days:
            count += 1
            day -= timedelta(days=1)
        return count

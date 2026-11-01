from datetime import date

import pytest

from guitarapp.history import History, SessionRecord


def rec(title, when, bpm, correct, total=10):
    return SessionRecord(title, when, bpm, total, correct)


def test_records_persist_and_stats(tmp_path):
    path = tmp_path / "h.json"
    h = History(path)
    h.add(rec("Spider", "2026-11-01T10:00:00", 60, 10))
    h.add(rec("Spider", "2026-11-01T10:05:00", 80, 7))
    h.add(rec("Spider", "2026-11-02T10:00:00", 70, 9))
    h.add(rec("Scale", "2026-11-02T11:00:00", 90, 5))

    again = History(path)
    stats = again.stats("Spider")
    assert stats.sessions == 3
    assert stats.best_accuracy == 1.0
    assert stats.best_clean_bpm == 70  # the 80 BPM run was not clean
    assert again.stats("Scale").best_clean_bpm is None
    assert [s.title for s in again.all_stats()] == ["Scale", "Spider"]
    assert again.stats("Nope") is None


def test_streak(tmp_path):
    h = History(tmp_path / "h.json")
    for day in ("2026-10-29", "2026-10-30", "2026-10-31", "2026-11-02"):
        h.add(rec("x", f"{day}T09:00:00", 60, 10))
    assert h.streak(today=date(2026, 11, 2)) == 1
    assert h.streak(today=date(2026, 11, 1)) == 3  # yesterday still counts
    assert h.streak(today=date(2026, 11, 5)) == 0


@pytest.mark.parametrize("content", [
    "{not json",
    '{"title": "x"}',
    '[{"title": "x", "when": "not-a-date", "bpm": 60, "total": 1, "correct": 1}]',
    '[{"title": "x", "when": "2026-11-01T10:00:00", "bpm": 60, "total": 1, "correct": 5}]',
    '[{"title": "x", "when": "2026-11-01T10:00:00", "bpm": -1, "total": 1, "correct": 1}]',
    '[{"title": "x", "when": "2026-11-01T10:00:00", "bpm": 60, "total": 1, "correct": 1, "extra": 1}]',
])
def test_broken_file_is_kept_aside_and_app_still_works(tmp_path, content):
    path = tmp_path / "h.json"
    path.write_text(content)
    h = History(path)
    assert h.records == [] and h.streak() == 0 and h.all_stats() == []
    assert not path.exists()
    assert len(list(tmp_path.glob("h.corrupt-*.json"))) == 1


def test_second_corruption_does_not_overwrite_first_backup(tmp_path):
    path = tmp_path / "h.json"
    for _ in range(2):
        path.write_text("{not json")
        History(path)
    assert len(list(tmp_path.glob("h.corrupt-*.json"))) == 2

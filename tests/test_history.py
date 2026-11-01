from datetime import date

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


def test_corrupt_file_is_kept_aside(tmp_path):
    path = tmp_path / "h.json"
    path.write_text("{not json")
    assert History(path).records == []
    assert (tmp_path / "h.corrupt.json").exists()

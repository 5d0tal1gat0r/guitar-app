import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from guitarapp.history import History, SessionRecord
from guitarapp.home import ActionCard, HomePage
from guitarapp.tabs import Exercise, Step

ROUTES = ["library", "tuner", "metronome", "theory", "quiz", "progress"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _exercise(title: str) -> Exercise:
    return Exercise(title=title, steps=[Step(beat=0, notes=((0, 0),))])


def _loader(count: int):
    return lambda: ([_exercise(f"Song {i}") for i in range(count)], [])


def _history(tmp_path, *titles: str) -> History:
    history = History(tmp_path / "history.json")
    for title in titles:
        history.add(SessionRecord(title=title, when=datetime.now().isoformat(), bpm=60, total=8, correct=7))
    return history


def _texts(page: HomePage) -> str:
    return "\n".join(label.text() for label in page.findChildren(QLabel))


def test_home_offers_six_routes_in_order(app, tmp_path):
    page = HomePage(_history(tmp_path), library_loader=_loader(0))
    assert [card.route for card in page.cards] == ROUTES
    for card in page.cards:
        assert isinstance(card, ActionCard)
        assert card.accessibleName()
        assert card.focusPolicy() & Qt.FocusPolicy.TabFocus


def test_click_space_and_enter_emit_route(app, tmp_path):
    page = HomePage(_history(tmp_path), library_loader=_loader(0))
    seen: list[str] = []
    page.route_requested.connect(seen.append)
    page.show()
    for card in page.cards:
        QTest.mouseClick(card, Qt.MouseButton.LeftButton)
        card.setFocus()
        QTest.keyClick(card, Qt.Key.Key_Space)
        QTest.keyClick(card, Qt.Key.Key_Return)
        QTest.keyClick(card, Qt.Key.Key_Enter)
    page.close()
    assert seen == [route for route in ROUTES for _ in range(4)]


def test_populated_summary_shows_real_numbers(app, tmp_path):
    page = HomePage(_history(tmp_path, "Scale run", "Riff study"), library_loader=_loader(30))
    page.refresh()
    text = _texts(page)
    assert "30 exercises" in text
    assert "1 day streak" in text
    assert page.recent_label.full_text == "Riff study"


def test_empty_state_is_honest(app, tmp_path):
    page = HomePage(_history(tmp_path), library_loader=_loader(0))
    page.refresh()
    text = _texts(page)
    assert "0 exercises" in text
    assert "0 day streak" in text
    assert page.recent_label.full_text == "No practice yet"


def test_single_exercise_is_singular(app, tmp_path):
    page = HomePage(_history(tmp_path), library_loader=_loader(1))
    page.refresh()
    assert "1 exercise" in _texts(page)
    assert "1 exercises" not in _texts(page)


def test_long_recent_title_does_not_widen_home(app, tmp_path):
    page = HomePage(_history(tmp_path, "x" * 120), library_loader=_loader(3))
    page.refresh()
    assert page.minimumSizeHint().width() <= 560


def test_microphone_state_copy(app, tmp_path):
    page = HomePage(_history(tmp_path), library_loader=_loader(0))
    page.set_microphone_state(True)
    assert "Microphone ready" in _texts(page)
    page.set_microphone_state(False)
    text = _texts(page)
    assert "Microphone off" in text
    assert "Microphone ready" not in text


def test_refresh_picks_up_new_practice(app, tmp_path):
    history = _history(tmp_path)
    page = HomePage(history, library_loader=_loader(2))
    page.refresh()
    history.add(SessionRecord(title="New song", when=datetime.now().isoformat(), bpm=60, total=4, correct=4))
    page.refresh()
    assert page.recent_label.full_text == "New song"

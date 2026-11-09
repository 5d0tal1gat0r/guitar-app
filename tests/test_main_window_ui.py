import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from guitarapp.history import History
from guitarapp.tabs import Exercise, Step
from guitarapp.ui import MainWindow

ROUTES = ["home", "library", "practice", "tuner", "metronome", "theory", "quiz", "progress"]


@pytest.fixture
def window(app, tmp_path):
    win = MainWindow(history=History(tmp_path / "history.json"), start_audio=False)
    win.show()
    app.processEvents()
    yield win
    win.close()


def test_home_is_initial_route(window):
    assert window.current_route == "home"
    assert window.stack.currentWidget() is window.pages["home"]
    assert window.route_buttons["home"].isChecked()


def test_all_routes_exist(window):
    assert list(window.pages) == ROUTES
    assert list(window.route_buttons) == ROUTES


def test_sidebar_click_selects_page_and_active_button(window):
    for route in ROUTES:
        QTest.mouseClick(window.route_buttons[route], Qt.MouseButton.LeftButton)
        assert window.current_route == route
        assert window.stack.currentWidget() is window.pages[route]
        checked = [r for r, b in window.route_buttons.items() if b.isChecked()]
        assert checked == [route]


def test_home_cards_route_through_shell(window):
    for card in window.home_page.cards:
        window.show_route("home")
        card.click()
        assert window.current_route == card.route


def test_returning_home_refreshes_summary(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window.home_page, "refresh", lambda: calls.append(1))
    window.show_route("tuner")
    window.show_route("home")
    assert calls == [1]


def test_open_practice_loads_exercise_and_selects_practice(window):
    exercise = Exercise(title="Shell test", steps=[Step(beat=0, notes=((0, 0),))])
    window.open_practice(exercise)
    assert window.current_route == "practice"
    assert window.practice_page.exercise is exercise


def test_space_only_toggles_practice_and_metronome(window, monkeypatch):
    toggled = []
    monkeypatch.setattr(window.metronome_page, "toggle", lambda: toggled.append("metronome"))
    monkeypatch.setattr(window.practice_page, "toggle", lambda: toggled.append("practice"))
    window.show_route("home")
    window.on_space()
    window.show_route("metronome")
    window.on_space()
    window.open_practice(Exercise(title="x", steps=[Step(beat=0, notes=((0, 0),))]))
    window.on_space()
    window.show_route("tuner")
    window.on_space()
    assert toggled == ["metronome", "practice"]


def test_mic_off_updates_toolbar_and_home(window):
    window.toggle_mic(False)
    assert not window.hub.running
    assert window.listen.text() == "Mic off"
    assert window.home_page.mic_label.text() == "Microphone off"


def test_mic_on_success_updates_home(window, monkeypatch):
    monkeypatch.setattr(window.hub, "start", lambda device=None: True)
    window.toggle_mic(True)
    assert window.home_page.mic_label.text() == "Microphone ready"
    window.hub.start = lambda device=None: False
    window.toggle_mic(True)
    assert window.home_page.mic_label.text() == "Microphone off"


def test_route_buttons_are_accessible_and_focusable(window):
    for route, button in window.route_buttons.items():
        assert button.accessibleName()
        assert button.focusPolicy() & Qt.FocusPolicy.TabFocus
        assert not button.icon().isNull()


def test_route_buttons_activate_from_keyboard(window):
    button = window.route_buttons["theory"]
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert window.current_route == "theory"

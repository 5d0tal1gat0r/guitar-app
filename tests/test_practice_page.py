import pytest
from PySide6.QtTest import QTest

from guitarapp.history import History
from guitarapp.pitch import NoteReading
from guitarapp.practice import Verdict
from guitarapp.tabs import Exercise, Step
from guitarapp.ui import LOOP_PAUSE_MS, AudioHub, MainWindow

EXERCISE = Exercise(
    title="Four notes",
    steps=[Step(0, ((1, 0),)), Step(1, ((1, 2),)), Step(2, ((1, 3),)), Step(3, ((1, 5),))],
    bpm=60,
)


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(AudioHub, "running", property(lambda self: True))
    win = MainWindow(history=History(tmp_path / "history.json"), start_audio=False)
    page = win.practice_page
    page.now = 100.0
    page.clock = lambda: page.now
    page.click.setChecked(False)
    win.show()
    yield win
    win.close()


def play_run(page, hit: set[int]):
    """Play the current session: steps in `hit` correct, the rest missed."""
    session = page.session
    for index, step in enumerate(session.exercise.steps):
        page.now = session.step_start(index) + 0.02
        page._tick()
        if index in hit:
            page.on_note(NoteReading(session.exercise.midi_notes(step)[0], 2.0, 0.0))
    page.now = session.step_end(len(session.exercise.steps) - 1) + 0.5
    page._tick()


def test_starts_empty_and_routes_to_library(window):
    page = window.practice_page
    assert page.views.currentWidget() is page.empty_view
    assert not page.controls.isVisible()
    window.show_route("practice")
    [button] = [b for b in page.empty_view.findChildren(type(page.start_button)) if b.text() == "Open Library"]
    button.click()
    assert window.current_route == "library"


def test_load_shows_live_view_and_full_range(window):
    page = window.practice_page
    window.open_practice(EXERCISE)
    assert page.views.currentWidget() is page.live_view
    assert page.controls.isVisible()
    assert page.selected_range() == (0, 3)
    assert page.tab.loop_range is None


def test_tab_clicks_set_the_section(window):
    page = window.practice_page
    window.open_practice(EXERCISE)
    page.tab.step_clicked.emit(1, False)
    page.tab.step_clicked.emit(2, True)
    assert page.selected_range() == (1, 2)
    assert page.tab.loop_range == (1, 2)
    page.first_step.setValue(4)  # start after the end drags the end along
    assert page.selected_range() == (3, 3)


def test_finished_run_shows_results_and_records_history(window):
    page = window.practice_page
    window.open_practice(EXERCISE)
    page.start()
    play_run(page, hit={0, 1, 2, 3})
    assert page.views.currentWidget() is page.results_view
    assert page.result_score.text() == "100%"
    assert page.suggested_bpm == 65
    assert page.history.records[-1].title == "Four notes"
    assert page.result_tab.verdicts == {i: Verdict.CORRECT for i in range(4)}
    page.suggested_button.click()
    assert page.session is not None and page.session.bpm == 65


def test_section_run_is_recorded_under_its_own_title(window):
    page = window.practice_page
    window.open_practice(EXERCISE)
    page.tab.step_clicked.emit(1, False)
    page.tab.step_clicked.emit(2, True)
    page.start()
    assert len(page.session.exercise.steps) == 2
    play_run(page, hit={0})
    assert page.history.records[-1].title == "Four notes · steps 2–3"
    assert page.result_tab.verdicts == {1: Verdict.CORRECT, 2: Verdict.MISSED}


def test_loop_with_adapt_restarts_faster(window, app):
    page = window.practice_page
    window.open_practice(EXERCISE)
    page.loop.setChecked(True)
    page.adapt.setChecked(True)
    page.tempo_step.setValue(4)
    page.start()
    play_run(page, hit={0, 1, 2, 3})
    assert page.views.currentWidget() is page.live_view
    assert page.runs == 1
    assert page.bpm.value() == 64
    QTest.qWait(LOOP_PAUSE_MS + 200)
    assert page.session is not None and page.session.bpm == 64
    assert page.runs == 1
    play_run(page, hit=set())
    assert page.runs == 2 and page.bpm.value() == 60


def test_adapt_respects_the_goal(window):
    page = window.practice_page
    window.open_practice(EXERCISE)
    page.loop.setChecked(True)
    page.adapt.setChecked(True)
    page.goal.setValue(62)
    page.start()
    play_run(page, hit={0, 1, 2, 3})
    assert page.bpm.value() == 62


def test_stop_during_loop_pause_cancels_restart(window, app):
    page = window.practice_page
    window.open_practice(EXERCISE)
    page.loop.setChecked(True)
    page.start()
    play_run(page, hit={0})
    page.toggle()  # Stop while waiting for the next run
    QTest.qWait(LOOP_PAUSE_MS + 200)
    assert page.session is None
    assert page.start_button.text() == "Start"


def test_loop_without_adapt_keeps_tempo(window):
    page = window.practice_page
    window.open_practice(EXERCISE)
    page.loop.setChecked(True)
    page.start()
    play_run(page, hit={0, 1, 2, 3})
    assert page.bpm.value() == 60

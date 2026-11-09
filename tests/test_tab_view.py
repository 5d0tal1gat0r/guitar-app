from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from guitarapp.practice import Verdict
from guitarapp.tabs import Exercise, Step
from guitarapp.widgets import TabView


def _exercise(n=40):
    return Exercise(title="t", steps=[Step(i, ((i % 6, i % 12),)) for i in range(n)])


def test_current_step_stays_in_view(app):
    view = TabView()
    view.resize(400, 150)
    view.set_exercise(_exercise())
    for index in (0, 5, 20, 39):
        view.set_current(index)
        x = view.column_x(index)
        assert 0 <= x <= view.width() - view.COLUMN
    view.set_current(20)
    # Upcoming steps get most of the room: current sits in the left third.
    assert view.column_x(20) <= view.width() / 3


def test_verdicts_and_reset(app):
    view = TabView()
    view.set_exercise(_exercise(4))
    view.set_verdict(1, Verdict.WRONG)
    assert view.verdicts == {1: Verdict.WRONG}
    view.reset()
    assert view.verdicts == {} and view.current is None


def test_loop_range_and_click_selection(app):
    view = TabView()
    view.resize(600, 150)
    view.set_exercise(_exercise(10))
    view.show()
    clicked = []
    view.step_clicked.connect(lambda i, shift: clicked.append((i, shift)))
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     QPoint(int(view.column_x(3)) + 5, 60))
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                     QPoint(int(view.column_x(6)) + 5, 60))
    assert clicked == [(3, False), (6, True)]
    view.set_range(3, 6)
    assert view.loop_range == (3, 6)
    view.close()


def test_paints_without_exercise(app):
    view = TabView()
    view.resize(300, 120)
    assert not view.grab().isNull()

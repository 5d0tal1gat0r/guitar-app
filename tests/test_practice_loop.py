import pytest

from guitarapp.practice import next_tempo, section
from guitarapp.tabs import Exercise, Step

EX = Exercise(
    title="Riff",
    steps=[Step(0, ((1, 0),)), Step(1, ((1, 2),)), Step(2.5, ((1, 3),), duration=0.5), Step(4, ((1, 5),), duration=2)],
    bpm=70,
    description="d",
)


def test_section_rebases_beats_and_keeps_settings():
    part = section(EX, 1, 2)
    assert [s.beat for s in part.steps] == [0, 1.5]
    assert [s.notes for s in part.steps] == [((1, 2),), ((1, 3),)]
    assert part.bpm == 70 and part.tuning == EX.tuning
    assert part.title == "Riff · steps 2–3"


def test_section_last_step_lasts_until_next_original_step():
    part = section(EX, 1, 2)
    # Step 3 originally runs from beat 2.5 to beat 4 (the next step's start).
    assert part.steps[-1].duration == 1.5


def test_section_ending_on_last_step_keeps_its_duration():
    part = section(EX, 2, 3)
    assert part.steps[-1].duration == 2


def test_full_section_is_the_exercise_itself():
    assert section(EX, 0, 3) is EX


@pytest.mark.parametrize("first,last", [(-1, 2), (2, 1), (0, 4)])
def test_section_rejects_bad_ranges(first, last):
    with pytest.raises(ValueError):
        section(EX, first, last)


def test_next_tempo_rewards_clean_runs():
    assert next_tempo(60, 0.95) == 65
    assert next_tempo(60, 0.9, step=10) == 70


def test_next_tempo_holds_in_between():
    assert next_tempo(60, 0.75) == 60


def test_next_tempo_backs_off_sloppy_runs():
    assert next_tempo(60, 0.5) == 55
    assert next_tempo(22, 0.1) == 20  # never below MIN_BPM


def test_next_tempo_stops_at_target():
    assert next_tempo(78, 1.0, target=80) == 80
    assert next_tempo(80, 1.0, target=80) == 80

# test_seed_fake_data.py -- the demo seed script can be re-run without duplicating data.

import pytest

from app_logic.workout_repository import WorkoutRepository
from scripts.seed_fake_data import seed


@pytest.fixture
def repo(tmp_path):
    return WorkoutRepository(str(tmp_path / "test.db"))


def test_seed_loads_demo_sets(repo):
    seed(repo)

    assert len(repo.get_all_sets()) == 10
    assert repo.get_all_exercises() == ["Bench Press", "Deadlift", "Overhead Press", "Squat"]


def test_seed_twice_does_not_duplicate(repo):
    seed(repo)
    seed(repo)

    assert len(repo.get_all_sets()) == 10


def test_seed_keeps_manually_logged_sets(repo):
    from datetime import date

    repo.add_set("Bench Press", 130, 6, date.today(), planned_reps=10, notes="shoulder pain again")
    seed(repo)
    seed(repo)

    assert len(repo.get_all_sets()) == 11

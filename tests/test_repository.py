# test_repository.py -- quick checks that the math is right (OWNER: either).

from datetime import date, timedelta

import pytest

from app_logic.workout_repository import WorkoutRepository

TODAY = date.today()


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


@pytest.fixture
def repo(tmp_path):
    return WorkoutRepository(str(tmp_path / "test.db"))


# ---- Setup / reads ----

def test_creates_missing_data_folder(tmp_path):
    db_path = tmp_path / "nested" / "data" / "repiq.db"
    WorkoutRepository(str(db_path))
    assert db_path.exists()


def test_recent_sets_are_newest_first_and_limited(repo):
    repo.add_set("Bench Press", 135, 10, days_ago(3), planned_reps=10, notes="old")
    repo.add_set("Bench Press", 145, 8, days_ago(1), planned_reps=10, notes="new")
    repo.add_set("Bench Press", 140, 9, days_ago(2))

    recent = repo.get_recent_sets("Bench Press", limit=2)

    assert [s.weight for s in recent] == [145, 140]
    assert recent[0].notes == "new"
    assert recent[0].logged_on == days_ago(1)


def test_recent_sets_only_returns_that_exercise(repo):
    repo.add_set("Bench Press", 135, 10, days_ago(1))
    repo.add_set("Squat", 225, 5, days_ago(1))

    assert [s.exercise for s in repo.get_recent_sets("Squat")] == ["Squat"]


def test_get_all_sets_newest_first(repo):
    repo.add_set("Squat", 225, 5, days_ago(5))
    repo.add_set("Bench Press", 135, 10, days_ago(1))

    assert [s.exercise for s in repo.get_all_sets()] == ["Bench Press", "Squat"]


def test_get_all_exercises_is_distinct_and_sorted(repo):
    repo.add_set("Squat", 225, 5, days_ago(2))
    repo.add_set("Bench Press", 135, 10, days_ago(1))
    repo.add_set("Squat", 230, 5, days_ago(1))

    assert repo.get_all_exercises() == ["Bench Press", "Squat"]


def test_empty_database(repo):
    assert repo.get_all_sets() == []
    assert repo.get_all_exercises() == []


# ---- Weekly volume ----

def test_weekly_volume_sums_weight_times_reps(repo):
    repo.add_set("Bench Press", 100, 10, days_ago(1))  # 1000
    repo.add_set("Bench Press", 150, 5, days_ago(3))   # 750

    assert repo.calculate_weekly_volume("Bench Press") == 1750


def test_weekly_volume_ignores_sets_older_than_7_days(repo):
    repo.add_set("Bench Press", 100, 10, days_ago(7))  # on the cutoff -> counted
    repo.add_set("Bench Press", 999, 10, days_ago(8))  # too old -> ignored

    assert repo.calculate_weekly_volume("Bench Press") == 1000


def test_weekly_volume_ignores_other_exercises(repo):
    repo.add_set("Bench Press", 100, 10, days_ago(1))
    repo.add_set("Squat", 200, 5, days_ago(1))

    assert repo.calculate_weekly_volume("Bench Press") == 1000


def test_weekly_volume_is_zero_with_no_data(repo):
    assert repo.calculate_weekly_volume("Bench Press") == 0.0


# ---- 1RM estimate (Epley) ----

def test_one_rep_max_uses_epley_on_most_recent_set(repo):
    repo.add_set("Bench Press", 200, 3, days_ago(5))
    repo.add_set("Bench Press", 150, 10, days_ago(1))  # 150 * (1 + 10/30) = 200.0

    assert repo.estimate_one_rep_max("Bench Press") == 200.0


def test_one_rep_max_is_rounded_to_one_decimal(repo):
    repo.add_set("Bench Press", 135, 8, days_ago(1))  # 135 * (1 + 8/30) = 171.0
    repo.add_set("Squat", 185, 7, days_ago(1))        # 185 * (1 + 7/30) = 228.166...

    assert repo.estimate_one_rep_max("Bench Press") == 171.0
    assert repo.estimate_one_rep_max("Squat") == 228.2


def test_one_rep_max_is_none_with_no_data(repo):
    assert repo.estimate_one_rep_max("Bench Press") is None


# ---- Progression curve ----

def test_progression_curve_is_oldest_first_within_window(repo):
    repo.add_set("Bench Press", 150, 10, days_ago(1))
    repo.add_set("Bench Press", 120, 10, days_ago(14))
    repo.add_set("Bench Press", 300, 10, days_ago(70))  # outside 8 weeks

    curve = repo.get_progression_curve("Bench Press", weeks=8)

    assert curve == [
        (days_ago(14).isoformat(), 160.0),
        (days_ago(1).isoformat(), 200.0),
    ]


def test_progression_curve_respects_weeks_argument(repo):
    repo.add_set("Bench Press", 150, 10, days_ago(1))
    repo.add_set("Bench Press", 120, 10, days_ago(14))

    assert len(repo.get_progression_curve("Bench Press", weeks=1)) == 1


# ---- Rep deficit ----

def test_rep_deficit_when_reps_missed(repo):
    repo.add_set("Bench Press", 135, 8, days_ago(1), planned_reps=10)

    assert repo.get_rep_deficit("Bench Press") == 2


def test_rep_deficit_is_negative_when_target_beaten(repo):
    repo.add_set("Bench Press", 135, 12, days_ago(1), planned_reps=10)

    assert repo.get_rep_deficit("Bench Press") == -2


def test_rep_deficit_uses_most_recent_set(repo):
    repo.add_set("Bench Press", 135, 5, days_ago(5), planned_reps=10)
    repo.add_set("Bench Press", 135, 10, days_ago(1), planned_reps=10)

    assert repo.get_rep_deficit("Bench Press") == 0


def test_rep_deficit_is_none_without_planned_reps(repo):
    repo.add_set("Bench Press", 135, 8, days_ago(1))

    assert repo.get_rep_deficit("Bench Press") is None


def test_rep_deficit_is_none_with_no_data(repo):
    assert repo.get_rep_deficit("Bench Press") is None

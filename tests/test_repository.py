# test_repository.py -- quick checks that the math is right (OWNER: either).

from datetime import date, timedelta

import pytest

from sqlalchemy import create_engine, text

from app_logic.workout_repository import (
    DEFAULT_DATABASE_URL,
    WorkoutRepository,
    get_database_url,
)

TODAY = date.today()


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


# ---- Setup / reads ----

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


# ---- Re-runnable imports (source tracking) ----

def test_add_set_defaults_to_manual_source(repo):
    repo.add_set("Bench Press", 135, 10, days_ago(1))
    repo.replace_sets_from_source("seed", [])

    assert len(repo.get_all_sets()) == 1


def test_replace_sets_from_source_does_not_duplicate(repo):
    sets = [{"exercise": "Squat", "weight": 225, "reps": 5, "logged_on": days_ago(1)}]

    repo.replace_sets_from_source("seed", sets)
    repo.replace_sets_from_source("seed", sets)

    assert len(repo.get_all_sets()) == 1


def test_replace_sets_from_source_keeps_other_sources(repo):
    repo.add_set("Bench Press", 135, 10, days_ago(1))
    repo.replace_sets_from_source("sheets", [{"exercise": "Squat", "weight": 225, "reps": 5, "logged_on": days_ago(1)}])

    repo.replace_sets_from_source("seed", [{"exercise": "Deadlift", "weight": 315, "reps": 3, "logged_on": days_ago(1)}])

    assert repo.get_all_exercises() == ["Bench Press", "Deadlift", "Squat"]


def test_identical_manual_sets_are_both_kept(repo):
    # Three sets of 135 x 10 on one day is a normal workout, not a duplicate.
    repo.add_set("Bench Press", 135, 10, days_ago(1))
    repo.add_set("Bench Press", 135, 10, days_ago(1))

    assert len(repo.get_all_sets()) == 2


def test_replace_rolls_back_if_a_set_is_invalid(repo):
    good = {"exercise": "Squat", "weight": 225, "reps": 5, "logged_on": days_ago(1)}
    repo.replace_sets_from_source("sheets", [good])

    with pytest.raises(KeyError):
        repo.replace_sets_from_source("sheets", [good, {"exercise": "Squat"}])

    assert len(repo.get_all_sets()) == 1  # the earlier import is still there


def test_adds_source_column_to_old_database(make_repo, database_url):
    # Simulate a database created before the `source` column existed.
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text(
            """CREATE TABLE sets (id INTEGER PRIMARY KEY, exercise VARCHAR(200) NOT NULL,
               weight FLOAT NOT NULL, reps INTEGER NOT NULL, planned_reps INTEGER,
               notes TEXT NOT NULL DEFAULT '', logged_on DATE NOT NULL)"""
        ))
        conn.execute(text(
            "INSERT INTO sets (id, exercise, weight, reps, logged_on) VALUES (1, 'Squat', 225, 5, '2026-10-01')"
        ))
    engine.dispose()

    repo = make_repo()
    repo.replace_sets_from_source("seed", [])

    assert [s.exercise for s in repo.get_all_sets()] == ["Squat"]  # old row kept, treated as manual


# ---- Database layer (PostgreSQL / SQLAlchemy) ----

def test_creating_repository_twice_keeps_data(make_repo):
    make_repo().add_set("Squat", 225, 5, days_ago(1))

    assert len(make_repo().get_all_sets()) == 1  # CREATE TABLE IF NOT EXISTS, no wipe


def test_logged_on_round_trips_as_a_date(repo):
    repo.add_set("Squat", 225, 5, date(2026, 2, 28))

    logged_on = repo.get_all_sets()[0].logged_on
    assert type(logged_on) is date
    assert logged_on == date(2026, 2, 28)


def test_fractional_weights_are_preserved(repo):
    repo.add_set("Curl", 27.5, 12, days_ago(1))

    assert repo.get_all_sets()[0].weight == 27.5
    assert repo.calculate_weekly_volume("Curl") == 330.0


def test_weekly_volume_returns_a_float(repo):
    repo.add_set("Squat", 200, 5, days_ago(1))

    assert isinstance(repo.calculate_weekly_volume("Squat"), float)


def test_same_day_sets_ordered_by_insertion(repo):
    repo.add_set("Bench Press", 135, 10, days_ago(1), planned_reps=10)
    repo.add_set("Bench Press", 135, 7, days_ago(1), planned_reps=10)

    # The last set logged that day counts as "most recent".
    assert repo.get_rep_deficit("Bench Press") == 3


def test_exercise_names_with_quotes_are_stored_safely(repo):
    name = "Farmer's Walk'); DROP TABLE sets; --"
    repo.add_set(name, 100, 1, days_ago(1))

    assert repo.get_all_exercises() == [name]
    assert len(repo.get_recent_sets(name)) == 1


def test_uses_database_url_from_environment(monkeypatch, database_url):
    monkeypatch.setenv("DATABASE_URL", database_url)

    repo = WorkoutRepository()
    try:
        assert repo.database_url == database_url
    finally:
        repo.dispose()


@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_database_url_is_normalised_to_psycopg(monkeypatch, given, expected):
    monkeypatch.setenv("DATABASE_URL", given)

    assert get_database_url() == expected


def test_default_database_url_points_at_local_postgres(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("app_logic.workout_repository.load_dotenv", lambda: None)

    assert get_database_url() == DEFAULT_DATABASE_URL
    assert DEFAULT_DATABASE_URL.startswith("postgresql+psycopg://")

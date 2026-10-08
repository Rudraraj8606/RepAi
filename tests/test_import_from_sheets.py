# test_import_from_sheets.py -- checks Sheet rows -> database (no Google connection needed).

from datetime import date

import pytest

from app_logic.workout_repository import WorkoutRepository
from scripts.import_from_sheets import import_rows


@pytest.fixture
def repo(tmp_path):
    return WorkoutRepository(str(tmp_path / "test.db"))


def test_imports_rows_like_get_all_records_returns(repo):
    # gspread's get_all_records() gives numbers as ints and blanks as "".
    rows = [
        {"date": "2026-09-20", "exercise": "Bench Press", "weight": 145, "reps": 9,
         "planned_reps": 10, "notes": "good session"},
        {"date": "2026-09-21", "exercise": " Squat ", "weight": "185.5", "reps": "5",
         "planned_reps": "", "notes": ""},
    ]

    assert import_rows(repo, rows) == 2

    squat, bench = repo.get_all_sets()
    assert (bench.exercise, bench.weight, bench.reps, bench.planned_reps, bench.notes) == (
        "Bench Press", 145.0, 9, 10, "good session"
    )
    assert bench.logged_on == date(2026, 9, 20)
    assert (squat.exercise, squat.weight, squat.planned_reps) == ("Squat", 185.5, None)


def test_skips_blank_rows(repo):
    rows = [
        {"date": "", "exercise": "", "weight": "", "reps": "", "planned_reps": "", "notes": ""},
        {"date": "2026-09-20", "exercise": "", "weight": 100, "reps": 5},
        {"date": "", "exercise": "Bench Press", "weight": 100, "reps": 5},
        {"date": "2026-09-20", "exercise": "Bench Press", "weight": 100, "reps": 5},
    ]

    assert import_rows(repo, rows) == 1
    assert len(repo.get_all_sets()) == 1


def test_missing_notes_column_is_fine(repo):
    rows = [{"date": "2026-09-20", "exercise": "Deadlift", "weight": 225, "reps": 5}]

    import_rows(repo, rows)

    assert repo.get_all_sets()[0].notes == ""

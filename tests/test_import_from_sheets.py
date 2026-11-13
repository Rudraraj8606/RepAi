# test_import_from_sheets.py -- checks Sheet rows -> database (no Google connection needed).
#
# Rows use the real Sheet's headers:
#   Date | Workout | Planned Sets/Reps | Sets/Reps | Weight | Notes
# and one Sheet row can become several database rows (one per set).

from datetime import date

import pytest

import scripts.import_from_sheets as import_from_sheets
from scripts.import_from_sheets import import_rows


def make_row(workout="Bench Press", day="2026-09-20", planned="1x10", actual="1x9",
             weight="145lbs", notes=""):
    """One Sheet row, shaped like gspread's get_all_records() returns it."""
    return {
        "Date": day,
        "Workout": workout,
        "Planned Sets/Reps": planned,
        "Sets/Reps": actual,
        "Weight": weight,
        "Notes": notes,
    }


# ---- The original seven tests, translated to the new layout ----

def test_imports_rows_like_get_all_records_returns(repo):
    # gspread's get_all_records() gives plain numbers as ints/floats and blanks as "".
    rows = [
        {"Date": "2026-09-20", "Workout": "Bench Press", "Planned Sets/Reps": "1x10",
         "Sets/Reps": "1x9", "Weight": 145, "Notes": "good session"},
        {"Date": "2026-09-21", "Workout": " Squat ", "Planned Sets/Reps": "",
         "Sets/Reps": "1x5", "Weight": "185.5lbs", "Notes": ""},
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
        make_row(workout="", day="", planned="", actual="", weight=""),   # fully blank
        make_row(workout="", actual="1x5", weight="100lbs"),               # no exercise
        make_row(day="", actual="1x5", weight="100lbs"),                   # no date
        make_row(actual="1x5", weight="100lbs"),                           # the one good row
    ]

    assert import_rows(repo, rows) == 1
    assert len(repo.get_all_sets()) == 1


def test_missing_notes_column_is_fine(repo, capsys):
    row = make_row("Deadlift", planned="1x5", actual="1x5", weight="225lbs")
    del row["Notes"]

    import_rows(repo, [row])

    assert repo.get_all_sets()[0].notes == ""
    assert "Notes" in capsys.readouterr().out   # ...but it warns, so a typo'd header isn't silent


def test_reimport_replaces_instead_of_duplicating(repo):
    rows = [make_row()]

    import_rows(repo, rows)
    import_rows(repo, rows)

    assert len(repo.get_all_sets()) == 1


def test_reimport_reflects_edits_and_deleted_rows(repo):
    import_rows(repo, [
        make_row("Bench Press", weight="145lbs"),
        make_row("Squat", day="2026-09-21", planned="1x5", actual="1x5", weight="185lbs"),
    ])

    import_rows(repo, [make_row("Bench Press", weight="150lbs")])

    [only] = repo.get_all_sets()
    assert (only.exercise, only.weight) == ("Bench Press", 150.0)


def test_reimport_keeps_sets_logged_in_the_web_form(repo):
    repo.add_set("Deadlift", 315, 3, date(2026, 9, 22))

    import_rows(repo, [make_row()])
    import_rows(repo, [make_row()])

    assert repo.get_all_exercises() == ["Bench Press", "Deadlift"]


def test_bad_row_aborts_before_deleting_previous_import(repo):
    import_rows(repo, [make_row()])

    # A date that can't be read still aborts the whole import. (A non-numeric
    # weight no longer does: "BW" is normal in the Sheet, so those rows are skipped.)
    with pytest.raises(ValueError):
        import_rows(repo, [make_row("Squat", day="not a date", weight="185lbs")])

    assert repo.get_all_exercises() == ["Bench Press"]


# ---- New: how one Sheet row becomes database rows ----

def test_sets_x_reps_expands_into_one_row_per_set(repo):
    import_rows(repo, [make_row("Incline DB Press", planned="4x8-10", actual="4x10", weight="55lbs")])

    sets = repo.get_all_sets()
    assert len(sets) == 4
    assert all((s.reps, s.weight) == (10, 55.0) for s in sets)


def test_uneven_sets_are_read_set_by_set(repo):
    import_rows(repo, [make_row("Chest Flys", planned="4x8-10", actual="2x8, 2x7", weight="70lbs")])

    assert sorted(s.reps for s in repo.get_all_sets()) == [7, 7, 8, 8]


@pytest.mark.parametrize("planned, expected", [
    ("4x8-10", 8),        # rep range: the bottom of the range
    ("3x12", 12),         # a single target
    ("2-3x10-15", 10),    # a range of sets AND a range of reps
    ("", None),           # no plan written down
])
def test_planned_reps_are_read_from_the_plan(repo, planned, expected):
    import_rows(repo, [make_row(planned=planned, actual="1x9")])

    assert repo.get_all_sets()[0].planned_reps == expected


def test_top_of_range_option(repo, monkeypatch):
    monkeypatch.setattr(import_from_sheets, "USE_TOP_OF_RANGE", True)

    import_rows(repo, [make_row(planned="4x8-10", actual="1x9")])

    assert repo.get_all_sets()[0].planned_reps == 10


def test_note_is_kept_on_every_set_of_the_exercise(repo):
    import_rows(repo, [make_row("Hack Squats", planned="3x8-10", actual="3x8",
                                weight="115lbs", notes="legs cramping")])

    assert [s.notes for s in repo.get_all_sets()] == ["legs cramping"] * 3


def test_reads_dates_the_way_google_sheets_displays_them(repo):
    import_rows(repo, [make_row(day="2/7/2026")])

    assert repo.get_all_sets()[0].logged_on == date(2026, 2, 7)


def test_plan_left_in_the_workout_name_is_stripped(repo):
    import_rows(repo, [make_row("Standing Calf Raises, 4x8-10", planned="4x8-10",
                                actual="4x10", weight="130lbs")])

    assert repo.get_all_exercises() == ["Standing Calf Raises"]


# ---- New: rows that aren't weight x reps lifts, and wrong headers ----

def test_non_lifting_rows_are_skipped_and_listed(repo, capsys):
    rows = [
        make_row("Dips", planned="4x8-10", actual="4x10", weight="BW"),
        make_row("1-Min Plank", planned="3x1min", actual="3x1min", weight="BW"),
        make_row("10k Steps", planned="10k steps", actual="10k steps", weight="-"),
        make_row("Hack Squats", planned="3x8-10", actual="3x8", weight="175lbs"),
    ]

    assert import_rows(repo, rows) == 3   # only the three Hack Squats sets
    assert repo.get_all_exercises() == ["Hack Squats"]

    printed = capsys.readouterr().out
    assert "Skipped 3 row(s)" in printed
    assert "Dips" in printed


def test_wrong_headers_fail_loudly(repo):
    old_style = {"date": "2026-09-20", "exercise": "Bench Press", "weight": 145, "reps": 9}

    with pytest.raises(ValueError, match="Missing column"):
        import_rows(repo, [old_style])

    assert repo.get_all_sets() == []
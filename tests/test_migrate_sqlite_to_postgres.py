# test_migrate_sqlite_to_postgres.py -- copying an old SQLite file into the new database.

import sqlite3
from datetime import date

import pytest

from scripts.migrate_sqlite_to_postgres import migrate, read_sqlite_sets


def make_old_sqlite(path, with_source=True):
    conn = sqlite3.connect(path)
    source_col = ", source TEXT NOT NULL DEFAULT 'manual'" if with_source else ""
    conn.execute(
        f"""CREATE TABLE sets (id INTEGER PRIMARY KEY AUTOINCREMENT, exercise TEXT NOT NULL,
            weight REAL NOT NULL, reps INTEGER NOT NULL, planned_reps INTEGER,
            notes TEXT DEFAULT '', logged_on TEXT NOT NULL{source_col})"""
    )
    if with_source:
        conn.executemany(
            "INSERT INTO sets (exercise, weight, reps, planned_reps, notes, logged_on, source) VALUES (?,?,?,?,?,?,?)",
            [
                ("Squat", 225, 5, 5, "solid", "2026-10-01", "seed"),
                ("Bench Press", 135.5, 8, 10, "", "2026-10-02", "manual"),
                ("Deadlift", 315, 3, None, None, "2026-10-03", "sheets"),
            ],
        )
    else:
        conn.execute("INSERT INTO sets (exercise, weight, reps, logged_on) VALUES ('Squat', 225, 5, '2026-10-01')")
    conn.commit()
    conn.close()
    return str(path)


def test_copies_every_set_with_its_source(tmp_path, repo):
    old = make_old_sqlite(tmp_path / "old.db")

    assert migrate(old, repo) == 3

    assert repo.get_all_exercises() == ["Bench Press", "Deadlift", "Squat"]
    bench = repo.get_recent_sets("Bench Press")[0]
    assert (bench.weight, bench.reps, bench.planned_reps, bench.logged_on) == (135.5, 8, 10, date(2026, 10, 2))
    # sources kept: replacing "seed" removes only the seeded Squat
    repo.replace_sets_from_source("seed", [])
    assert repo.get_all_exercises() == ["Bench Press", "Deadlift"]


def test_null_notes_become_empty_strings(tmp_path, repo):
    migrate(make_old_sqlite(tmp_path / "old.db"), repo)

    assert repo.get_recent_sets("Deadlift")[0].notes == ""


def test_old_file_without_source_column_is_treated_as_manual(tmp_path):
    sets = read_sqlite_sets(make_old_sqlite(tmp_path / "old.db", with_source=False))

    assert [s["source"] for s in sets] == ["manual"]


def test_refuses_to_duplicate_into_non_empty_database(tmp_path, repo):
    old = make_old_sqlite(tmp_path / "old.db")
    migrate(old, repo)

    with pytest.raises(RuntimeError):
        migrate(old, repo)
    assert len(repo.get_all_sets()) == 3


def test_force_appends(tmp_path, repo):
    old = make_old_sqlite(tmp_path / "old.db")
    migrate(old, repo)

    migrate(old, repo, force=True)

    assert len(repo.get_all_sets()) == 6


def test_file_without_sets_table_is_an_error(tmp_path, repo):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()

    with pytest.raises(ValueError):
        migrate(str(empty), repo)

"""
migrate_sqlite_to_postgres.py  --  copy an old SQLite database into PostgreSQL.

One-time helper for anyone who used RepIQ before the switch to Postgres.
Reads every set from the old SQLite file (default: data/repiq.db) and inserts
it into the database in DATABASE_URL, keeping each set's `source`.

Run (from the RepAi/ folder, with Postgres running):
    python -m scripts.migrate_sqlite_to_postgres                 # default file
    python -m scripts.migrate_sqlite_to_postgres path/to/old.db  # another file

Refuses to run if the target already has sets (so it can't create duplicates);
pass --force to append anyway.
"""

import argparse
import sqlite3
from datetime import date

from app_logic.workout_repository import WorkoutRepository


def read_sqlite_sets(sqlite_path: str) -> list[dict]:
    """Every row of the old `sets` table as a dict (oldest first)."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(sets)")}
        if not columns:
            raise ValueError(f"{sqlite_path} has no `sets` table.")
        source = "source" if "source" in columns else "'manual'"
        rows = conn.execute(
            f"SELECT exercise, weight, reps, planned_reps, notes, logged_on, {source} AS source "
            "FROM sets ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "exercise": r["exercise"],
            "weight": float(r["weight"]),
            "reps": int(r["reps"]),
            "planned_reps": r["planned_reps"],
            "notes": r["notes"] or "",
            "logged_on": date.fromisoformat(r["logged_on"]),
            "source": r["source"],
        }
        for r in rows
    ]


def migrate(sqlite_path: str, repo: WorkoutRepository, force: bool = False) -> int:
    """Copy all sets into `repo`. Returns how many were copied."""
    sets = read_sqlite_sets(sqlite_path)
    if repo.get_all_sets() and not force:
        raise RuntimeError("Target database already has sets; re-run with --force to append.")
    with repo.engine.begin() as conn:  # one transaction: all rows or none
        for s in sets:
            repo._insert_set(
                conn, s["exercise"], s["weight"], s["reps"], s["logged_on"],
                s["planned_reps"], s["notes"], s["source"],
            )
    return len(sets)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sqlite_path", nargs="?", default="data/repiq.db")
    parser.add_argument("--force", action="store_true", help="append even if target has data")
    args = parser.parse_args()

    repo = WorkoutRepository()
    count = migrate(args.sqlite_path, repo, force=args.force)
    print(f"Copied {count} sets from {args.sqlite_path} into {repo.engine.url.render_as_string(hide_password=True)}.")

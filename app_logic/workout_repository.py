"""
workout_repository.py

Custom Application Logic layer for RepIQ.

This class is the Python equivalent of the `LibraryCatalog` class in the
Java example: it owns the database connection and contains every
*deterministic* calculation (no LLM calls happen in here). Agent 1 and
Agent 2 never touch the database directly -- they only see the results
that this class produces, exposed to them through WorkoutTools.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass
class SetEntry:
    exercise: str
    weight: float
    reps: int
    planned_reps: Optional[int]
    notes: str
    logged_on: date


class WorkoutRepository:
    """Owns the SQLite connection and all deterministic training-metric math."""

    def __init__(self, db_path: str = "repiq.db"):
        self.db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exercise TEXT NOT NULL,
                    weight REAL NOT NULL,
                    reps INTEGER NOT NULL,
                    planned_reps INTEGER,
                    notes TEXT DEFAULT '',
                    logged_on TEXT NOT NULL
                )
                """
            )

    # ---- Ingestion (fed by the Google Sheets import script) ----

    def add_set(
        self,
        exercise: str,
        weight: float,
        reps: int,
        logged_on: date,
        planned_reps: Optional[int] = None,
        notes: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sets (exercise, weight, reps, planned_reps, notes, logged_on)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (exercise, weight, reps, planned_reps, notes, logged_on.isoformat()),
            )

    # ---- Reads used internally by the calculations below ----

    def get_recent_sets(self, exercise: str, limit: int = 10) -> list[SetEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT exercise, weight, reps, planned_reps, notes, logged_on
                FROM sets WHERE exercise = ?
                ORDER BY logged_on DESC LIMIT ?
                """,
                (exercise, limit),
            ).fetchall()
        return [
            SetEntry(
                exercise=r["exercise"],
                weight=r["weight"],
                reps=r["reps"],
                planned_reps=r["planned_reps"],
                notes=r["notes"],
                logged_on=date.fromisoformat(r["logged_on"]),
            )
            for r in rows
        ]

    # ---- Deterministic calculations (the "custom application logic") ----

    def calculate_weekly_volume(self, exercise: str) -> float:
        """Total weight x reps lifted for an exercise in the last 7 days."""
        cutoff = date.today() - timedelta(days=7)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT SUM(weight * reps) AS volume
                FROM sets WHERE exercise = ? AND logged_on >= ?
                """,
                (exercise, cutoff.isoformat()),
            ).fetchone()
        return row["volume"] or 0.0

    def estimate_one_rep_max(self, exercise: str) -> Optional[float]:
        """Epley formula 1RM estimate from the most recent set."""
        recent = self.get_recent_sets(exercise, limit=1)
        if not recent:
            return None
        s = recent[0]
        return round(s.weight * (1 + s.reps / 30), 1)

    def get_progression_curve(self, exercise: str, weeks: int = 8) -> list[tuple[str, float]]:
        """(date, estimated 1RM) pairs for the last N weeks, oldest first."""
        cutoff = date.today() - timedelta(weeks=weeks)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT weight, reps, logged_on FROM sets
                WHERE exercise = ? AND logged_on >= ?
                ORDER BY logged_on ASC
                """,
                (exercise, cutoff.isoformat()),
            ).fetchall()
        return [
            (r["logged_on"], round(r["weight"] * (1 + r["reps"] / 30), 1)) for r in rows
        ]

    def get_rep_deficit(self, exercise: str) -> Optional[int]:
        """Planned reps minus actual reps on the most recent set (missed reps)."""
        recent = self.get_recent_sets(exercise, limit=1)
        if not recent or recent[0].planned_reps is None:
            return None
        return recent[0].planned_reps - recent[0].reps
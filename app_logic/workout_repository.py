"""
workout_repository.py

Custom Application Logic layer for RepIQ.

This class is the Python equivalent of the `LibraryCatalog` class in the
Java example: it owns the database connection and contains every
*deterministic* calculation (no LLM calls happen in here). Agent 1 and
Agent 2 never touch the database directly -- they only see the results
that this class produces, exposed to them through WorkoutTools.

Database: PostgreSQL, accessed through SQLAlchemy Core. The connection string
comes from the DATABASE_URL environment variable (loaded from .env), e.g.

    DATABASE_URL=postgresql+psycopg://repai:repai@localhost:5432/repai

Because SQLAlchemy abstracts the driver, any SQLAlchemy URL works -- the test
suite also runs against a throwaway SQLite file when no Postgres is configured.
"""

import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import (
    Column,
    Date,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    func,
    insert,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Connection, Engine

DEFAULT_DATABASE_URL = "postgresql+psycopg://repai:repai@localhost:5432/repai"

metadata = MetaData()

sets_table = Table(
    "sets",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("exercise", String(200), nullable=False, index=True),
    Column("weight", Float, nullable=False),
    Column("reps", Integer, nullable=False),
    Column("planned_reps", Integer),
    Column("notes", Text, nullable=False, server_default=""),
    Column("logged_on", Date, nullable=False, index=True),
    Column("source", String(20), nullable=False, server_default="manual", index=True),
)


def get_database_url() -> str:
    """DATABASE_URL from the environment / .env, or the local Docker default."""
    load_dotenv()
    url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    # Hosted providers (Render, Heroku, Neon...) hand out "postgres://" or
    # "postgresql://" URLs; point SQLAlchemy at the psycopg 3 driver we install.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@dataclass
class SetEntry:
    exercise: str
    weight: float
    reps: int
    planned_reps: Optional[int]
    notes: str
    logged_on: date


class WorkoutRepository:
    """Owns the database connection and all deterministic training-metric math."""

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or get_database_url()
        # pool_pre_ping drops dead connections (e.g. after Postgres restarts).
        self.engine: Engine = create_engine(self.database_url, pool_pre_ping=True)
        self._init_schema()

    def _init_schema(self) -> None:
        metadata.create_all(self.engine)  # CREATE TABLE IF NOT EXISTS
        # Databases created before the `source` column existed get it added here.
        columns = {c["name"] for c in inspect(self.engine).get_columns("sets")}
        if "source" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text("ALTER TABLE sets ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'manual'"))

    def dispose(self) -> None:
        """Close every pooled connection (used by tests and scripts)."""
        self.engine.dispose()

    # ---- Ingestion ----
    # `source` records where a set came from: "manual" (web form), "seed"
    # (demo data) or "sheets" (Google Sheets import). Scripts re-run with
    # replace_sets_from_source(), so running them twice never duplicates data.

    def add_set(
        self,
        exercise: str,
        weight: float,
        reps: int,
        logged_on: date,
        planned_reps: Optional[int] = None,
        notes: str = "",
        source: str = "manual",
    ) -> None:
        with self.engine.begin() as conn:
            self._insert_set(conn, exercise, weight, reps, logged_on, planned_reps, notes, source)

    def replace_sets_from_source(self, source: str, sets: list[dict]) -> int:
        """Delete every set from `source`, then insert `sets` (dicts of add_set
        arguments). Runs as one transaction, so a failure leaves the old rows in place.
        Returns how many sets were inserted."""
        with self.engine.begin() as conn:
            conn.execute(delete(sets_table).where(sets_table.c.source == source))
            for s in sets:
                self._insert_set(
                    conn,
                    s["exercise"],
                    s["weight"],
                    s["reps"],
                    s["logged_on"],
                    s.get("planned_reps"),
                    s.get("notes", ""),
                    source,
                )
        return len(sets)

    @staticmethod
    def _insert_set(
        conn: Connection, exercise, weight, reps, logged_on, planned_reps, notes, source
    ) -> None:
        conn.execute(
            insert(sets_table).values(
                exercise=exercise,
                weight=weight,
                reps=reps,
                planned_reps=planned_reps,
                notes=notes,
                logged_on=logged_on,
                source=source,
            )
        )

    # ---- Reads used internally by the calculations below ----

    _entry_columns = (
        sets_table.c.exercise,
        sets_table.c.weight,
        sets_table.c.reps,
        sets_table.c.planned_reps,
        sets_table.c.notes,
        sets_table.c.logged_on,
    )

    @staticmethod
    def _to_entry(row) -> SetEntry:
        return SetEntry(
            exercise=row.exercise,
            weight=row.weight,
            reps=row.reps,
            planned_reps=row.planned_reps,
            notes=row.notes,
            logged_on=row.logged_on,
        )

    def get_recent_sets(self, exercise: str, limit: int = 10) -> list[SetEntry]:
        query = (
            select(*self._entry_columns)
            .where(sets_table.c.exercise == exercise)
            .order_by(sets_table.c.logged_on.desc(), sets_table.c.id.desc())
            .limit(limit)
        )
        with self.engine.connect() as conn:
            return [self._to_entry(r) for r in conn.execute(query)]

    def get_all_sets(self) -> list[SetEntry]:
        """Every logged set, newest first (used by the history page)."""
        query = select(*self._entry_columns).order_by(
            sets_table.c.logged_on.desc(), sets_table.c.id.desc()
        )
        with self.engine.connect() as conn:
            return [self._to_entry(r) for r in conn.execute(query)]

    def get_all_exercises(self) -> list[str]:
        """Distinct exercise names that have at least one logged set."""
        query = select(sets_table.c.exercise).distinct().order_by(sets_table.c.exercise)
        with self.engine.connect() as conn:
            return list(conn.scalars(query))

    # ---- Deterministic calculations (the "custom application logic") ----

    def calculate_weekly_volume(self, exercise: str) -> float:
        """Total weight x reps lifted for an exercise in the last 7 days."""
        cutoff = date.today() - timedelta(days=7)
        query = select(func.sum(sets_table.c.weight * sets_table.c.reps)).where(
            sets_table.c.exercise == exercise, sets_table.c.logged_on >= cutoff
        )
        with self.engine.connect() as conn:
            volume = conn.scalar(query)
        return float(volume) if volume is not None else 0.0

    def estimate_one_rep_max(self, exercise: str) -> Optional[float]:
        """Epley formula 1RM estimate from the most recent set."""
        recent = self.get_recent_sets(exercise, limit=1)
        if not recent:
            return None
        s = recent[0]
        return round(s.weight * (1 + s.reps / 30), 1)

    def get_progression_curve(self, exercise: str, weeks: int = 8) -> list[tuple[str, float]]:
        """(ISO date, estimated 1RM) pairs for the last N weeks, oldest first."""
        cutoff = date.today() - timedelta(weeks=weeks)
        query = (
            select(sets_table.c.weight, sets_table.c.reps, sets_table.c.logged_on)
            .where(sets_table.c.exercise == exercise, sets_table.c.logged_on >= cutoff)
            .order_by(sets_table.c.logged_on.asc(), sets_table.c.id.asc())
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query).all()
        return [(r.logged_on.isoformat(), round(r.weight * (1 + r.reps / 30), 1)) for r in rows]

    def get_rep_deficit(self, exercise: str) -> Optional[int]:
        """Planned reps minus actual reps on the most recent set (missed reps)."""
        recent = self.get_recent_sets(exercise, limit=1)
        if not recent or recent[0].planned_reps is None:
            return None
        return recent[0].planned_reps - recent[0].reps

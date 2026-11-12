# conftest.py -- shared fixtures. Every test gets an empty database.
#
# Which database the tests use:
#   * TEST_DATABASE_URL set (e.g. the repai_test DB from docker-compose)
#       -> real PostgreSQL; the `sets` table is dropped before each test.
#   * not set -> a throwaway SQLite file in pytest's tmp_path, so the suite
#       still runs on a laptop without Postgres.
# Your real DATABASE_URL is never used by the tests.

import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app_logic.workout_repository import WorkoutRepository, metadata

load_dotenv()


@pytest.fixture
def database_url(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return f"sqlite:///{tmp_path / 'test.db'}"
    if url == os.environ.get("DATABASE_URL"):
        pytest.exit("TEST_DATABASE_URL must not be the same as DATABASE_URL -- tests wipe it.")
    _create_postgres_database_if_missing(url)
    return url


_created = set()


def _create_postgres_database_if_missing(url):
    """Create e.g. `repai_test` on first use (connects to the `postgres` maintenance DB)."""
    if url in _created or not url.startswith("postgresql"):
        return
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()
    _created.add(url)


@pytest.fixture
def make_repo(database_url):
    """Factory that returns a WorkoutRepository on a freshly emptied database."""
    repos = []

    def _make(url=None):
        repo = WorkoutRepository(url or database_url)
        repos.append(repo)
        return repo

    # Start from a clean schema on Postgres (SQLite files are already new).
    cleaner = WorkoutRepository(database_url)
    metadata.drop_all(cleaner.engine)
    cleaner.dispose()

    yield _make
    for repo in repos:
        repo.dispose()


@pytest.fixture
def repo(make_repo):
    return make_repo()


@pytest.fixture
def is_postgres(database_url):
    return database_url.startswith("postgresql")

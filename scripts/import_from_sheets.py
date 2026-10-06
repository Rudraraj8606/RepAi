"""
import_from_sheets.py  --  Google Sheet -> SQLite loader.  (YOUR FILE / A)

What it does:
  Reads each row of a user's workout Google Sheet and saves it into the
  database by calling repo.add_set(...). After this runs, the whole app has
  real data to work with.

Expected columns in the Sheet (first row = headers, exactly these names):
  date | exercise | weight | reps | planned_reps | notes
  e.g.  2026-09-20 | Bench Press | 145 | 9 | 10 | good session

Setup (one time):
  1. pip install gspread google-auth
  2. In Google Cloud, make a "service account", download its credentials.json,
     and put that file in the project root.
  3. Share your Google Sheet with the service account's email (looks like
     xxxx@yyyy.iam.gserviceaccount.com) so it's allowed to read the Sheet.
  4. Put your Sheet's name in SHEET_NAME below.

Run (from the repiq_project/ folder):
    python -m scripts.import_from_sheets
"""

from datetime import date

import gspread
from google.oauth2.service_account import Credentials

from app_logic.workout_repository import WorkoutRepository

DB_PATH = "data/repiq.db"
CREDENTIALS_FILE = "credentials.json"
SHEET_NAME = "RepIQ Workout Log"   # <-- change to your Sheet's name

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def read_rows_from_sheet() -> list[dict]:
    """Connect to Google Sheets and return each row as a dict keyed by header."""
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    worksheet = client.open(SHEET_NAME).sheet1
    return worksheet.get_all_records()   # list of {header: value} dicts


def import_rows(repo: WorkoutRepository, rows: list[dict]) -> int:
    """Save each Sheet row into the database. Returns how many were imported."""
    imported = 0
    for row in rows:
        # Skip blank / malformed rows instead of crashing the whole import.
        if not row.get("exercise") or not row.get("date"):
            continue

        planned = row.get("planned_reps")
        repo.add_set(
            exercise=str(row["exercise"]).strip(),
            weight=float(row["weight"]),
            reps=int(row["reps"]),
            logged_on=date.fromisoformat(str(row["date"]).strip()),
            planned_reps=int(planned) if planned not in (None, "") else None,
            notes=str(row.get("notes", "")).strip(),
        )
        imported += 1
    return imported


if __name__ == "__main__":
    repo = WorkoutRepository(DB_PATH)
    rows = read_rows_from_sheet()
    count = import_rows(repo, rows)
    print(f"Imported {count} sets from '{SHEET_NAME}' into {DB_PATH}.")

"""
import_from_sheets.py  --  Google Sheet -> PostgreSQL loader.  (YOUR FILE / A)

What it does:
  Reads each row of the workout-log Google Sheet and saves it into the
  database through repo.replace_sets_from_source(...). After this runs, the
  whole app has real data to work with.

Expected columns in the Sheet (first row = headers, exactly these names):
  Date | Workout | Planned Sets/Reps | Sets/Reps | Weight | Notes
  e.g.  2/7/2026 | Incline DB Press | 4x8-10 | 4x10 | 55lbs |

How one Sheet row becomes database rows (one database row per SET):
  - Sets/Reps "4x10" means 4 sets of 10 reps, so 4 rows. "2x8, 2x7" works too.
  - Planned Sets/Reps "4x8-10" sets planned_reps to 8 (the bottom of the rep
    range), so a "rep deficit" only shows up when you fall below your range.
    Set USE_TOP_OF_RANGE = True to compare against the top (10) instead.
  - Weight "55lbs" becomes 55.0.
  - Rows that are not weight x reps lifts (bodyweight, planks, steps) are
    skipped, and listed when the import finishes.

Setup (one time) -- put these two lines in your .env file:
  GOOGLE_CREDENTIALS_FILE=credentials/<your-service-account-key>.json
  SPREADSHEET_ID=<the long string in the Sheet's URL between /d/ and /edit>
  Then share the Sheet (Viewer) with the service account's client_email.
  Also: pip install gspread google-auth python-dotenv

Run (from the RepAi/ folder):
    python -m scripts.import_from_sheets

Safe to run again: each import replaces the sets from the previous import, so
the database always mirrors the Sheet (edits and deleted rows included).
Sets logged through the web form are kept.
"""

import os
import re
from datetime import date, datetime

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from app_logic.workout_repository import WorkoutRepository

load_dotenv()

CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Header names exactly as they appear in row 1 of the Sheet.
COL_DATE = "Date"
COL_WORKOUT = "Workout"
COL_PLANNED = "Planned Sets/Reps"
COL_ACTUAL = "Sets/Reps"
COL_WEIGHT = "Weight"
COL_NOTES = "Notes"

# For a planned "4x8-10": count a miss against 8 (False) or against 10 (True)?
USE_TOP_OF_RANGE = False

SETS_X_REPS = re.compile(r"^(\d+)\s*x\s*(\d+)$", re.IGNORECASE)                       # 4x10
PLANNED = re.compile(r"^(\d+)(?:-\d+)?\s*x\s*(\d+)(?:-(\d+))?$", re.IGNORECASE)        # 4x8-10, 2-3x10-15
WEIGHT = re.compile(r"^(\d+(?:\.\d+)?)\s*(?:lbs?)?$", re.IGNORECASE)                   # 55lbs, 17.5lbs, 55
PLAN_IN_NAME = re.compile(r",?\s*\d+(?:-\d+)?\s*x\s*\d+(?:-\d+)?\s*$", re.IGNORECASE)  # "Calf Raises, 4x8-10"


def parse_date(value) -> date:
    """Accept '2/7/2026' (how Google Sheets displays dates) or '2026-02-07'."""
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unrecognized date in sheet: {text!r}")


def parse_actual_sets(value) -> list[int] | None:
    """'4x10' -> [10, 10, 10, 10];  '2x8, 2x7' -> [8, 8, 7, 7].  None if it isn't sets x reps."""
    reps_per_set = []
    for chunk in str(value).split(","):
        match = SETS_X_REPS.match(chunk.strip())
        if not match:
            return None
        sets, reps = int(match.group(1)), int(match.group(2))
        reps_per_set.extend([reps] * sets)
    return reps_per_set


def parse_planned_reps(value) -> int | None:
    """'4x8-10' -> 8 (or 10 if USE_TOP_OF_RANGE).  None if there's no usable plan."""
    match = PLANNED.match(str(value).strip())
    if not match:
        return None
    low, high = match.group(2), match.group(3)
    return int(high) if (USE_TOP_OF_RANGE and high) else int(low)


def parse_weight(value) -> float | None:
    """'55lbs' -> 55.0.  None for 'BW', '-', '35lbs/side' and anything else that isn't a plain weight."""
    match = WEIGHT.match(str(value).strip())
    return float(match.group(1)) if match else None


def clean_exercise_name(value) -> str:
    """Strip a plan accidentally left in the name: 'Calf Raises, 4x8-10' -> 'Calf Raises'."""
    return PLAN_IN_NAME.sub("", str(value)).strip()


def read_rows_from_sheet() -> list[dict]:
    """Connect to Google Sheets and return each row as a dict keyed by header."""
    if not CREDENTIALS_FILE or not SPREADSHEET_ID:
        raise RuntimeError(
            "Set GOOGLE_CREDENTIALS_FILE and SPREADSHEET_ID in your .env file."
        )
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    worksheet = client.open_by_key(SPREADSHEET_ID).sheet1
    return worksheet.get_all_records()   # list of {header: value} dicts


def import_rows(repo: WorkoutRepository, rows: list[dict]) -> int:
    """Replace previously imported Sheet sets with `rows`. Returns how many sets were imported."""
    # Fail loudly on a header mismatch. Without this, a typo in a header would
    # silently drop that column's data (or import 0 sets) with no error.
    if rows:
        required = [COL_DATE, COL_WORKOUT, COL_PLANNED, COL_ACTUAL, COL_WEIGHT]
        missing = [name for name in required if name not in rows[0]]
        if missing:
            raise ValueError(
                f"Missing column(s) {missing}. The Sheet's headers are: {list(rows[0])}"
            )
        if COL_NOTES not in rows[0]:
            # Notes are optional, but say so out loud: a typo'd header would otherwise
            # silently drop every note.
            print(f"Warning: no '{COL_NOTES}' column found, so no notes will be imported.")

    # Parse every row first, so a bad row stops the import before anything is deleted.
    sets = []
    skipped = []
    for line_number, row in enumerate(rows, start=2):   # Sheet row 1 is the header
        exercise = clean_exercise_name(row.get(COL_WORKOUT, ""))
        if not exercise:
            continue   # blank row

        if not str(row.get(COL_DATE, "")).strip():
            skipped.append(f"row {line_number}: {exercise} (no date)")
            continue

        reps_per_set = parse_actual_sets(row.get(COL_ACTUAL, ""))
        weight = parse_weight(row.get(COL_WEIGHT, ""))
        if reps_per_set is None or weight is None:
            skipped.append(
                f"row {line_number}: {exercise} "
                f"({row.get(COL_ACTUAL, '')} @ {row.get(COL_WEIGHT, '')})"
            )
            continue

        try:
            logged_on = parse_date(row[COL_DATE])
        except ValueError as error:
            raise ValueError(f"Row {line_number}: {error}") from error

        planned = parse_planned_reps(row.get(COL_PLANNED, ""))
        notes = str(row.get(COL_NOTES, "")).strip()

        # The note describes the whole exercise that day, so every set carries it.
        for reps in reps_per_set:
            sets.append(
                {
                    "exercise": exercise,
                    "weight": weight,
                    "reps": reps,
                    "logged_on": logged_on,
                    "planned_reps": planned,
                    "notes": notes,
                }
            )

    if skipped:
        print(f"Skipped {len(skipped)} row(s) that aren't weight x reps lifts:")
        for item in skipped:
            print(f"  - {item}")

    return repo.replace_sets_from_source("sheets", sets)


if __name__ == "__main__":
    repo = WorkoutRepository()
    rows = read_rows_from_sheet()
    count = import_rows(repo, rows)
    print(f"Imported {count} sets from your Google Sheet into the database.")
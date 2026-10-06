"""
seed_fake_data.py  --  insert ~10 fake workouts, then print the calculations.

Run this FIRST (from the repiq_project/ folder):

    python -m scripts.seed_fake_data

If you see real numbers printed at the end, the whole app-logic layer works.
This is what unblocks the rest of the project: once data exists, you can build
the Flask pages and your friend can test the agents.
"""

from datetime import date, timedelta

from app_logic.workout_repository import WorkoutRepository

DB_PATH = "data/repiq.db"


def seed(repo: WorkoutRepository) -> None:
    today = date.today()

    fake_sets = [
        ("Bench Press", 135, 10, 10, "felt strong", today - timedelta(days=21)),
        ("Bench Press", 140, 9, 10, "last rep grindy", today - timedelta(days=14)),
        ("Bench Press", 145, 9, 10, "good session", today - timedelta(days=7)),
        ("Bench Press", 135, 8, 10, "shoulder felt off", today - timedelta(days=1)),
        ("Squat", 185, 5, 5, "easy", today - timedelta(days=10)),
        ("Squat", 195, 5, 5, "solid", today - timedelta(days=6)),
        ("Squat", 205, 5, 5, "moved well", today - timedelta(days=2)),
        ("Deadlift", 225, 5, 5, "warm-up heavy", today - timedelta(days=9)),
        ("Deadlift", 245, 4, 5, "back tight", today - timedelta(days=3)),
        ("Overhead Press", 95, 6, 8, "shoulders tired", today - timedelta(days=4)),
    ]

    for exercise, weight, reps, planned, notes, logged_on in fake_sets:
        repo.add_set(
            exercise=exercise,
            weight=weight,
            reps=reps,
            planned_reps=planned,
            notes=notes,
            logged_on=logged_on,
        )
    print(f"Inserted {len(fake_sets)} fake sets.\n")


def print_metrics(repo: WorkoutRepository) -> None:
    for exercise in repo.get_all_exercises():
        print(f"=== {exercise} ===")
        print(f"  weekly volume : {repo.calculate_weekly_volume(exercise)} lbs")
        print(f"  estimated 1RM : {repo.estimate_one_rep_max(exercise)} lbs")
        print(f"  rep deficit   : {repo.get_rep_deficit(exercise)}")
        curve = repo.get_progression_curve(exercise)
        print(f"  progression   : {curve}\n")


if __name__ == "__main__":
    repo = WorkoutRepository(DB_PATH)
    seed(repo)
    print_metrics(repo)
    print("If you see numbers above, the app-logic layer works. You're ready to build.")

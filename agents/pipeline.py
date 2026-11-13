"""
pipeline.py  --  glue that runs Agent 1 then Agent 2  (OWNER: friend / B)

Runs the full Agent 1 -> Agent 2 chain for one exercise + note, and
returns both outputs so the Flask app can display them.
"""

from app_logic.workout_repository import WorkoutRepository
from agents.diagnostician_agent import diagnose
from agents.coach_agent import coach


def run_pipeline(repository: WorkoutRepository, exercise: str, user_note: str) -> dict:
    diagnosis = diagnose(repository, exercise, user_note)
    plan = coach(diagnosis, exercise)
    return {"diagnosis": diagnosis, "plan": plan}


if __name__ == "__main__":
    repo = WorkoutRepository()
    result = run_pipeline(repo, "Hack Squat", "legs felt tired and I was cramping, had to drop the weight")
    print("DIAGNOSIS:", result["diagnosis"])
    print("PLAN:", result["plan"])
"""
app.py  --  Flask web app.  (YOUR FILE / A)

Two pages:
  "/"            -> workout history + a quick metric summary per exercise
  "/coach/<ex>"  -> asks for a note on how the session felt, then runs the
                    AI pipeline (Agent 1 -> Agent 2) and shows the diagnosis + plan

Run (from the RepAi/ folder):
    python -m web.app
Then open http://127.0.0.1:5000 in your browser.
"""

from flask import Flask, render_template, request

from app_logic.workout_repository import WorkoutRepository

DB_PATH = "data/repiq.db"

app = Flask(__name__)
repo = WorkoutRepository(DB_PATH)


@app.route("/")
def history():
    sets = repo.get_all_sets()
    # Build a small summary row for each exercise using the deterministic math.
    summary = []
    for exercise in repo.get_all_exercises():
        summary.append(
            {
                "exercise": exercise,
                "weekly_volume": repo.calculate_weekly_volume(exercise),
                "one_rep_max": repo.estimate_one_rep_max(exercise),
                "rep_deficit": repo.get_rep_deficit(exercise),
            }
        )
    return render_template("history.html", sets=sets, summary=summary)


@app.route("/coach/<exercise>")
def coach(exercise):
    diagnosis, plan, error = None, None, None
    # Only run the pipeline once the user has submitted a note -- each run makes LLM calls.
    note = request.args.get("note")
    if note is not None:
        try:
            from agents.pipeline import run_pipeline
            result = run_pipeline(repo, exercise, note)
            diagnosis, plan = result["diagnosis"], result["plan"]
        except Exception as e:
            error = f"Something went wrong running the coach: {e}"

    return render_template(
        "coach.html", exercise=exercise, note=note, diagnosis=diagnosis, plan=plan, error=error
    )


if __name__ == "__main__":
    app.run(debug=True)

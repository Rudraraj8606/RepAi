"""
app.py  --  Flask web app.  (YOUR FILE / A)

Two pages:
  "/"            -> workout history + a quick metric summary per exercise
  "/coach/<ex>"  -> runs the AI pipeline and shows the diagnosis + plan

Run (from the repiq_project/ folder):
    python -m repiq.web.app
Then open http://127.0.0.1:5000 in your browser.

Note: the coaching page calls your friend's pipeline (Agent 1 -> Agent 2).
Until that's finished, the page shows a friendly "not ready yet" message
instead of crashing -- so you can build and test this site right now.
"""

from flask import Flask, render_template

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
    try:
        # Your friend builds this pipeline (Agent 1 -> Agent 2).
        from agents.pipeline import run_pipeline
        diagnosis, plan = run_pipeline(repo, exercise)
    except (ImportError, NotImplementedError):
        error = "The AI coaching pipeline isn't finished yet. Check back once Agent 2 is built."
    except Exception as e:
        error = f"Something went wrong running the coach: {e}"

    return render_template(
        "coach.html", exercise=exercise, diagnosis=diagnosis, plan=plan, error=error
    )


if __name__ == "__main__":
    app.run(debug=True)

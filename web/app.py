"""
app.py  --  Flask web app.  (YOUR FILE / A)

Two pages:
  "/"            -> workout history + a quick metric summary per exercise,
                    plus a form to log a new set (POSTs to "/add-set")
  "/coach/<ex>"  -> asks for a note on how the session felt, then runs the
                    AI pipeline (Agent 1 -> Agent 2) and shows the diagnosis + plan

Run (from the RepAi/ folder):
    python -m web.app
It starts on port 5000, or the next free port if 5000 is taken (on macOS,
AirPlay Receiver uses 5000). The terminal prints the URL to open.
Set PORT=xxxx to choose a starting port yourself.
"""

import os
import socket
from datetime import date

from flask import Flask, redirect, render_template, request, url_for

from app_logic.workout_repository import WorkoutRepository

DB_PATH = "data/repiq.db"

app = Flask(__name__)
repo = WorkoutRepository(DB_PATH)


@app.route("/")
def history():
    return render_history()


def render_history(error=None):
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
    return render_template(
        "history.html", sets=sets, summary=summary, error=error, today=date.today().isoformat()
    )


@app.route("/add-set", methods=["POST"])
def add_set():
    form = request.form
    try:
        exercise = form["exercise"].strip()
        if not exercise:
            raise ValueError("Exercise name is required.")
        planned = form.get("planned_reps", "").strip()
        repo.add_set(
            exercise=exercise,
            weight=float(form["weight"]),
            reps=int(form["reps"]),
            logged_on=date.fromisoformat(form["logged_on"]),
            planned_reps=int(planned) if planned else None,
            notes=form.get("notes", "").strip(),
        )
    except (KeyError, ValueError) as e:
        return render_history(error=f"Couldn't save that set: {e}"), 400
    # Redirect so refreshing the page doesn't submit the same set twice.
    return redirect(url_for("history"))


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


def find_free_port(start: int, attempts: int = 50) -> int:
    """Return the first port from `start` upward that nothing is listening on."""
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found between {start} and {start + attempts - 1}.")


if __name__ == "__main__":
    # Flask's debug reloader re-runs this file in a child process, so pick the
    # port once and hand it down through the environment.
    if "REPAI_PORT" not in os.environ:
        os.environ["REPAI_PORT"] = str(find_free_port(int(os.environ.get("PORT", 5000))))
        print(f"\n  RepIQ running at  http://127.0.0.1:{os.environ['REPAI_PORT']}\n")
    app.run(debug=True, port=int(os.environ["REPAI_PORT"]))

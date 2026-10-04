"""
workout_tools.py

Python equivalent of LibraryTools.java. Where LibraryTools wraps a
LibraryCatalog and exposes @Tool-annotated methods for an LLM agent,
WorkoutTools wraps a WorkoutRepository and exposes @tool-decorated
callables for Agent 1 (the Diagnostician). This lets Agent 1 decide
*which* metrics it needs to look at, rather than always being handed
every calculation up front.
"""

from langchain_core.tools import tool

from workout_repository import WorkoutRepository


class WorkoutTools:
    """Builds a list of LangChain tools bound to one WorkoutRepository instance."""

    def __init__(self, repository: WorkoutRepository):
        self.repository = repository

    def get_tools(self):
        repository = self.repository  # captured by the closures below

        @tool
        def list_recent_sets(exercise: str, limit: int = 5) -> str:
            """List the most recent logged sets for an exercise, including notes."""
            print(f"[Tool] list_recent_sets({exercise}, {limit})")
            sets = repository.get_recent_sets(exercise, limit)
            if not sets:
                return f"No logged sets found for {exercise}."
            lines = [
                f"{s.logged_on}: {s.weight} lbs x {s.reps} reps "
                f"(planned {s.planned_reps}) - notes: '{s.notes}'"
                for s in sets
            ]
            return "\n".join(lines)

        @tool
        def get_weekly_volume(exercise: str) -> str:
            """Get the total training volume (weight x reps) for an exercise over the last 7 days."""
            print(f"[Tool] get_weekly_volume({exercise})")
            volume = repository.calculate_weekly_volume(exercise)
            return f"Weekly volume for {exercise}: {volume} lbs total."

        @tool
        def get_one_rep_max_estimate(exercise: str) -> str:
            """Estimate the user's current one-rep max for an exercise from their most recent set."""
            print(f"[Tool] get_one_rep_max_estimate({exercise})")
            estimate = repository.estimate_one_rep_max(exercise)
            if estimate is None:
                return f"Not enough data to estimate a 1RM for {exercise}."
            return f"Estimated 1RM for {exercise}: {estimate} lbs."

        @tool
        def get_progression_trend(exercise: str, weeks: int = 8) -> str:
            """Get the estimated-1RM progression trend for an exercise over the last N weeks."""
            print(f"[Tool] get_progression_trend({exercise}, {weeks})")
            curve = repository.get_progression_curve(exercise, weeks)
            if not curve:
                return f"No progression history found for {exercise} in the last {weeks} weeks."
            return "\n".join(f"{d}: est. 1RM {rm} lbs" for d, rm in curve)

        @tool
        def get_rep_deficit(exercise: str) -> str:
            """Get how many reps short of the planned target the user was on their most recent set."""
            print(f"[Tool] get_rep_deficit({exercise})")
            deficit = repository.get_rep_deficit(exercise)
            if deficit is None:
                return f"No planned-vs-actual rep data available for {exercise}."
            if deficit <= 0:
                return f"User met or exceeded the planned reps for {exercise}."
            return f"User missed {deficit} rep(s) of the planned target for {exercise}."

        return [
            list_recent_sets,
            get_weekly_volume,
            get_one_rep_max_estimate,
            get_progression_trend,
            get_rep_deficit,
        ]
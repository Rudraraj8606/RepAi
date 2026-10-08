# test_workout_tools.py -- checks the text Agent 1 sees from each tool (no LLM calls).

from datetime import date, timedelta

import pytest

from app_logic.workout_repository import WorkoutRepository
from agents.workout_tools import WorkoutTools

TODAY = date.today()


@pytest.fixture
def repo(tmp_path):
    return WorkoutRepository(str(tmp_path / "test.db"))


def get_tool(repo, name):
    return {t.name: t for t in WorkoutTools(repo).get_tools()}[name]


def test_exposes_all_five_tools(repo):
    names = {t.name for t in WorkoutTools(repo).get_tools()}
    assert names == {
        "list_recent_sets",
        "get_weekly_volume",
        "get_one_rep_max_estimate",
        "get_progression_trend",
        "get_rep_deficit",
    }


def test_list_recent_sets_includes_notes(repo):
    repo.add_set("Bench Press", 135, 8, TODAY, planned_reps=10, notes="shoulder felt off")

    out = get_tool(repo, "list_recent_sets").invoke({"exercise": "Bench Press"})

    assert "135.0 lbs x 8 reps (planned 10)" in out
    assert "shoulder felt off" in out


def test_weekly_volume(repo):
    repo.add_set("Bench Press", 100, 10, TODAY)

    out = get_tool(repo, "get_weekly_volume").invoke({"exercise": "Bench Press"})

    assert out == "Weekly volume for Bench Press: 1000.0 lbs total."


def test_one_rep_max_estimate(repo):
    repo.add_set("Bench Press", 150, 10, TODAY)

    out = get_tool(repo, "get_one_rep_max_estimate").invoke({"exercise": "Bench Press"})

    assert out == "Estimated 1RM for Bench Press: 200.0 lbs."


def test_progression_trend(repo):
    repo.add_set("Bench Press", 120, 10, TODAY - timedelta(days=7))
    repo.add_set("Bench Press", 150, 10, TODAY)

    out = get_tool(repo, "get_progression_trend").invoke({"exercise": "Bench Press"})

    assert out.splitlines() == [
        f"{(TODAY - timedelta(days=7)).isoformat()}: est. 1RM 160.0 lbs",
        f"{TODAY.isoformat()}: est. 1RM 200.0 lbs",
    ]


def test_rep_deficit_missed(repo):
    repo.add_set("Bench Press", 135, 8, TODAY, planned_reps=10)

    out = get_tool(repo, "get_rep_deficit").invoke({"exercise": "Bench Press"})

    assert out == "User missed 2 rep(s) of the planned target for Bench Press."


def test_rep_deficit_met(repo):
    repo.add_set("Bench Press", 135, 10, TODAY, planned_reps=10)

    out = get_tool(repo, "get_rep_deficit").invoke({"exercise": "Bench Press"})

    assert out == "User met or exceeded the planned reps for Bench Press."


@pytest.mark.parametrize(
    "tool_name, expected",
    [
        ("list_recent_sets", "No logged sets found for Bench Press."),
        ("get_one_rep_max_estimate", "Not enough data to estimate a 1RM for Bench Press."),
        ("get_progression_trend", "No progression history found for Bench Press in the last 8 weeks."),
        ("get_rep_deficit", "No planned-vs-actual rep data available for Bench Press."),
    ],
)
def test_tools_report_missing_data_instead_of_crashing(repo, tool_name, expected):
    out = get_tool(repo, tool_name).invoke({"exercise": "Bench Press"})
    assert out == expected

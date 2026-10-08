# test_web_app.py -- checks the Flask pages against a temp database (pipeline faked out).

import sys
import types
from datetime import date

import pytest

import web.app as web_app
from app_logic.workout_repository import WorkoutRepository


@pytest.fixture
def repo(tmp_path, monkeypatch):
    test_repo = WorkoutRepository(str(tmp_path / "test.db"))
    monkeypatch.setattr(web_app, "repo", test_repo)
    return test_repo


@pytest.fixture
def client(repo):
    return web_app.app.test_client()


@pytest.fixture
def fake_pipeline(monkeypatch):
    """Replace agents.pipeline so the coach page never makes real API calls."""
    calls = []

    def run_pipeline(repository, exercise, user_note):
        calls.append((exercise, user_note))
        return {"diagnosis": "FAKE DIAGNOSIS", "plan": "FAKE PLAN"}

    module = types.ModuleType("agents.pipeline")
    module.run_pipeline = run_pipeline
    monkeypatch.setitem(sys.modules, "agents.pipeline", module)
    return calls


def valid_form(**overrides):
    form = {
        "logged_on": "2026-10-07",
        "exercise": "Bench Press",
        "weight": "130",
        "reps": "6",
        "planned_reps": "10",
        "notes": "shoulder pain again",
    }
    form.update(overrides)
    return form


# ---- History page ----

def test_history_page_loads_when_empty(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'action="/add-set"' in resp.get_data(as_text=True)


def test_history_page_shows_sets_and_summary(client, repo):
    repo.add_set("Bench Press", 135, 8, date.today(), planned_reps=10, notes="shoulder felt off")

    body = client.get("/").get_data(as_text=True)

    assert "shoulder felt off" in body
    assert 'href="/coach/Bench Press"' in body
    assert '<span class="miss">2</span>' in body


# ---- Add set form ----

def test_add_set_saves_and_redirects(client, repo):
    resp = client.post("/add-set", data=valid_form(exercise="  Bench Press  "))

    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"
    [saved] = repo.get_all_sets()
    assert (saved.exercise, saved.weight, saved.reps, saved.planned_reps, saved.notes) == (
        "Bench Press", 130.0, 6, 10, "shoulder pain again"
    )
    assert saved.logged_on == date(2026, 10, 7)


def test_add_set_planned_reps_is_optional(client, repo):
    resp = client.post("/add-set", data=valid_form(planned_reps=""))

    assert resp.status_code == 302
    assert repo.get_all_sets()[0].planned_reps is None


@pytest.mark.parametrize(
    "bad_field",
    [
        {"weight": "abc"},
        {"reps": "six"},
        {"logged_on": "10/07/2026"},
        {"exercise": "   "},
    ],
)
def test_add_set_rejects_bad_input(client, repo, bad_field):
    resp = client.post("/add-set", data=valid_form(**bad_field))

    assert resp.status_code == 400
    assert "Couldn&#39;t save that set" in resp.get_data(as_text=True)
    assert repo.get_all_sets() == []


def test_add_set_rejects_missing_field(client, repo):
    form = valid_form()
    del form["weight"]

    resp = client.post("/add-set", data=form)

    assert resp.status_code == 400
    assert repo.get_all_sets() == []


# ---- Coach page ----

def test_coach_page_without_note_does_not_run_pipeline(client, fake_pipeline):
    body = client.get("/coach/Bench Press").get_data(as_text=True)

    assert fake_pipeline == []
    assert "How did your last Bench Press session feel?" in body
    assert "FAKE DIAGNOSIS" not in body


def test_coach_page_with_note_shows_diagnosis_and_plan(client, fake_pipeline):
    resp = client.get("/coach/Bench Press", query_string={"note": "shoulder felt off"})
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert fake_pipeline == [("Bench Press", "shoulder felt off")]
    assert "FAKE DIAGNOSIS" in body
    assert "FAKE PLAN" in body


def test_coach_page_shows_error_if_pipeline_fails(client, monkeypatch):
    def broken_pipeline(repository, exercise, user_note):
        raise RuntimeError("API key missing")

    module = types.ModuleType("agents.pipeline")
    module.run_pipeline = broken_pipeline
    monkeypatch.setitem(sys.modules, "agents.pipeline", module)

    resp = client.get("/coach/Bench Press", query_string={"note": "tired"})

    assert resp.status_code == 200
    assert "Something went wrong running the coach: API key missing" in resp.get_data(as_text=True)

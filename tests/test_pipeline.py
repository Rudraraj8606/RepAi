# test_pipeline.py -- checks Agent 1 -> Agent 2 wiring with the LLM calls faked out.

import agents.pipeline as pipeline


def test_run_pipeline_passes_diagnosis_to_coach(monkeypatch):
    calls = {}

    def fake_diagnose(repository, exercise, user_note):
        calls["diagnose"] = (repository, exercise, user_note)
        return "shoulder strain suspected"

    def fake_coach(diagnosis):
        calls["coach"] = diagnosis
        return "deload to 115 lbs, 3x8"

    monkeypatch.setattr(pipeline, "diagnose", fake_diagnose)
    monkeypatch.setattr(pipeline, "coach", fake_coach)

    result = pipeline.run_pipeline("REPO", "Bench Press", "shoulder felt off")

    assert calls["diagnose"] == ("REPO", "Bench Press", "shoulder felt off")
    assert calls["coach"] == "shoulder strain suspected"
    assert result == {
        "diagnosis": "shoulder strain suspected",
        "plan": "deload to 115 lbs, 3x8",
    }

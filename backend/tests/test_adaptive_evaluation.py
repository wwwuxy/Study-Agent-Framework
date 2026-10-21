from copy import deepcopy
from pathlib import Path

import pytest


def test_dataset_integrity_splits_and_prediction_does_not_see_current_answer():
    from app.evaluation.dataset import load_dataset
    from app.evaluation.metrics import evaluate

    dataset = load_dataset(Path(__file__).parent / "fixtures/m3/sequences.json")
    result = evaluate(dataset)
    assert result["count"] > 0
    assert 0 <= result["brier_score"] <= 1
    changed = deepcopy(dataset)
    learner = next(s for s in changed["learners"] if s["split"] == "test")
    learner["events"][0]["correct"] = not learner["events"][0]["correct"]
    modified = evaluate(changed)
    assert modified["predictions"][0]["probability"] == result["predictions"][0]["probability"]
    leaked = deepcopy(dataset)
    leaked["learners"].append({**leaked["learners"][0], "split": "test"})
    with pytest.raises(ValueError, match="重复|划分"):
        evaluate(leaked)


def test_invalid_parameters_and_insufficient_optimizer_data_are_explicit():
    from app.evaluation.calibration import optimize_fsrs
    from app.learner.parameters import validate_parameter_artifact

    with pytest.raises(ValueError):
        validate_parameter_artifact({"bkt": {"guess": float("nan")}})
    with pytest.raises(ValueError, match="512|不足"):
        optimize_fsrs([], optimize_retention=False)


def test_parameter_rebuild_keeps_events_and_logs_immutable(client, settings):
    import asyncio
    import json

    from conftest import provider, register, space
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.db.models import ReviewLogRecord
    from app.evaluation.calibration import artifact
    from app.learner.parameters import BKTParameters, FSRSParameters, ParameterBundle
    from app.main import create_app
    from app.maintenance.rebuild_algorithms import rebuild_algorithms

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    q = client.post(root + "/diagnostics").json()["items"][0]
    client.post(root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": "a"})
    before = client.get(root + "/events").json()
    with client.app.state.session_factory() as db:
        original_logs = [
            (r.id, r.log, r.before, r.after, r.parameter_version) for r in db.scalars(select(ReviewLogRecord))
        ]
    params = artifact(
        ParameterBundle(
            bkt=BKTParameters(version="test-bkt", prior=0.3), fsrs=FSRSParameters(version="test-fsrs")
        ),
        "test-only",
    )
    params["status"] = "validated"
    result = asyncio.run(rebuild_algorithms(settings, params, "test-rebuild"))
    assert result["spaces_rebuilt"] == 1
    assert client.get(root + "/events").json() == before
    assert asyncio.run(rebuild_algorithms(settings, params, "test-rebuild")) == result
    with client.app.state.session_factory() as db:
        assert [
            (r.id, r.log, r.before, r.after, r.parameter_version) for r in db.scalars(select(ReviewLogRecord))
        ] == original_logs
    artifact_path = Path(settings.material_storage_dir).parent / "validated.json"
    artifact_path.write_text(json.dumps(params))
    with TestClient(
        create_app(settings.model_copy(update={"learner_parameters_path": str(artifact_path)}))
    ) as restarted:
        restarted.post("/api/v1/auth/login", json={"username": "alice", "password": "strong-password-2026"})
        assert restarted.get(root + "/profile").status_code == 200
        assert restarted.get(root + "/reviews").status_code == 200
        assert restarted.get(root + "/algorithms").json()["fsrs"]["parameter_version"] == "test-fsrs"

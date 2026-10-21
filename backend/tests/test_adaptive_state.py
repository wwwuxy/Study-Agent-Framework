from conftest import provider, register, space
from sqlalchemy import select


def test_every_new_space_initializes_both_algorithms_without_answer_evidence(client):
    from app.db.models import ReviewState

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    profile = client.get(root + "/profile").json()
    assert profile["estimator_version"] == "pybkt_v1"
    assert all(s["status"] == "unknown" and s["mastery_estimate"] is None for s in profile["states"])
    with client.app.state.session_factory() as db:
        cards = db.scalars(select(ReviewState).where(ReviewState.space_id == sid)).all()
        assert len(cards) == len(profile["states"])
        assert all(c.card["last_review"] is None for c in cards)
    events = client.get(root + "/events").json()
    assert client.post(root + "/profile/rebuild").json() == profile
    assert client.get(root + "/events").json() == events


def test_pybkt_is_used_for_api_answers_and_restart(client, settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    q = client.post(root + "/diagnostics").json()["items"][0]
    assert (
        client.post(
            root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": "a"}
        ).status_code
        == 201
    )
    before = client.get(root + "/profile").json()
    assert before["estimator_version"] == "pybkt_v1"
    state = next(s for s in before["states"] if s["concept_id"] == q["concept_keys"][0])
    assert state["mastery_estimate"] > 0.5
    restarted = create_app(settings)
    with TestClient(restarted) as other:
        other.post("/api/v1/auth/login", json={"username": "alice", "password": "strong-password-2026"})
        assert other.get(root + "/profile").json() == before


def test_fsrs_parameter_change_requires_rebuild_for_reads(client):
    from app.learner.parameters import FSRSParameters, ParameterBundle

    register(client)
    sid = space(client, provider(client))
    client.app.state.session_factory.configure(
        info={"algorithm_parameters": ParameterBundle(fsrs=FSRSParameters(version="changed"))}
    )
    response = client.get(f"/api/v1/study-spaces/{sid}/reviews")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "state_rebuild_required"

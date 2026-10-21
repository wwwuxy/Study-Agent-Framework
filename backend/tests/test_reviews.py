from datetime import timedelta

from conftest import provider, register, space
from sqlalchemy import select

from app.db.models import AgentRun, ReviewLogRecord, ReviewState, utcnow


def ready(client):
    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    q = next(q for q in client.post(root + "/diagnostics").json()["items"] if q["concept_keys"] == ["os"])
    client.post(root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": "first"})
    with client.app.state.session_factory() as db:
        card = db.scalar(
            select(ReviewState).where(ReviewState.space_id == sid, ReviewState.concept_id == "os")
        )
        due = utcnow() - timedelta(minutes=1)
        card.due, card.card = due, {**card.card, "due": due.isoformat()}
        db.commit()
    return sid, root, q


def test_reviews_are_read_only_and_unassessed_is_not_overdue(client):
    sid, root, _ = ready(client)
    before = client.get(root + "/events").json()
    with client.app.state.session_factory() as db:
        runs = len(db.scalars(select(AgentRun).where(AgentRun.space_id == sid)).all())
    response = client.get(root + "/reviews")
    assert response.status_code == 200, response.text
    assert [r["concept_id"] for r in response.json()["due"]] == ["os"]
    assert len(response.json()["unassessed"]) == 2
    assert client.get(root + "/events").json() == before
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(AgentRun).where(AgentRun.space_id == sid)).all()) == runs


def test_review_restores_new_question_and_cross_endpoint_submit_is_idempotent(client):
    sid, root, old_q = ready(client)
    started = client.post(root + "/reviews/start", json={"concept_id": "os", "idempotency_key": "review"})
    assert started.status_code == 201, started.text
    review = started.json()
    q = review["lesson"]["exercises"][0]
    assert q["prompt"] != old_q["prompt"]
    assert "answer" not in q
    assert (
        client.post(root + "/reviews/start", json={"concept_id": "os", "idempotency_key": "review"}).json()
        == review
    )
    body = {"item_id": q["id"], "answer": "A", "memory_rating": "hard", "idempotency_key": "submit-review"}
    result = client.post(root + f"/reviews/{review['id']}/submit", json=body)
    assert result.status_code == 201, result.text
    assert result.json()["memory"]["rating"] == 2
    assert client.post(root + "/attempts", json=body).json() == result.json()
    assert client.get(root + f"/reviews/{review['id']}").json()["status"] == "completed"
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(ReviewLogRecord).where(ReviewLogRecord.space_id == sid)).all()) == 2
    assert any(e["type"] == "review_submitted" for e in client.get(root + "/events").json())


def test_review_rejects_other_spaces_and_not_due_cards(client):
    _, root, _ = ready(client)
    started = client.post(
        root + "/reviews/start", json={"concept_id": "os", "idempotency_key": "review"}
    ).json()
    assert "id" in started
    client.post("/api/v1/auth/logout")
    register(client, "bob")
    assert client.get(root + f"/reviews/{started['id']}").status_code == 404

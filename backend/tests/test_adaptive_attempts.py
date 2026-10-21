from conftest import provider, register, space
from sqlalchemy import select

from app.db.models import LearningEvent, ReviewLogRecord, ReviewState


def setup(client):
    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    q = client.post(root + "/diagnostics").json()["items"][0]
    return sid, root, q


def test_one_answer_updates_bkt_fsrs_once_and_rebuild_does_not_reschedule(client):
    sid, root, q = setup(client)
    body = {"item_id": q["id"], "answer": "A", "idempotency_key": "answer", "memory_rating": "easy"}
    first = client.post(root + "/attempts", json=body)
    assert first.status_code == 201, first.text
    assert first.json()["memory"]["rating"] == 4
    assert client.post(root + "/attempts", json=body).json() == first.json()
    with client.app.state.session_factory() as db:
        logs = db.scalars(select(ReviewLogRecord).where(ReviewLogRecord.space_id == sid)).all()
        assert len(logs) == 1 and logs[0].log["rating"] == 4
        before = db.get(ReviewState, logs[0].state_id).card
    client.post(root + "/profile/rebuild")
    with client.app.state.session_factory() as db:
        assert db.get(ReviewState, logs[0].state_id).card == before


def test_hint_cannot_be_marked_easy_and_failure_rolls_back_all_evidence(client):
    sid, root, q = setup(client)
    client.post(root + f"/items/{q['id']}/hint", json={"idempotency_key": "hint"})
    response = client.post(
        root + "/attempts",
        json={"item_id": q["id"], "answer": "A", "idempotency_key": "answer", "memory_rating": "easy"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_memory_rating"
    with client.app.state.session_factory() as db:
        assert not db.scalars(select(ReviewLogRecord).where(ReviewLogRecord.space_id == sid)).all()
        assert not db.scalars(
            select(LearningEvent).where(
                LearningEvent.space_id == sid, LearningEvent.type == "diagnostic_submitted"
            )
        ).all()
    result = client.post(
        root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": "answer"}
    )
    assert result.status_code == 201
    assert result.json()["memory"]["rating"] == 1


def test_memory_library_failure_does_not_partially_commit_answer(client, monkeypatch):
    import app.reviews.state as state

    sid, root, q = setup(client)
    before = client.get(root + "/profile").json()

    def fail(*args, **kwargs):
        raise ValueError("invalid native state")

    monkeypatch.setattr(state, "review_card", fail)
    response = client.post(
        root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": "answer"}
    )
    assert response.status_code == 502
    assert client.get(root + "/profile").json() == before
    assert not any(e["type"] == "diagnostic_submitted" for e in client.get(root + "/events").json())

from conftest import provider, register, space
from sqlalchemy import select


def test_pause_does_not_complete_or_grade_and_resume_uses_original_questions(client):
    from app.db.models import Lesson, ReviewLogRecord, StudySpace
    from app.teaching.lifecycle import pause_current_lesson

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    lesson = client.post(root + "/lessons", json={"idempotency_key": "lesson"}).json()
    with client.app.state.session_factory() as db:
        s = db.get(StudySpace, sid)
        assert pause_current_lesson(db, s, reason="换重点", turn_id="test") == lesson["id"]
        db.commit()
        assert not db.get(Lesson, lesson["id"]).completed
        assert not list(db.scalars(select(ReviewLogRecord)))
    assert client.get(root + "/lessons/current").json() is None
    rows = client.get(root + "/lessons/paused").json()
    assert rows[0]["id"] == lesson["id"]
    restored = client.post(root + f"/lessons/{lesson['id']}/resume", json={"idempotency_key": "resume"})
    assert restored.status_code == 200, restored.text
    assert restored.json()["exercises"] == lesson["exercises"]


def test_resumed_old_lesson_wins_over_newer_completed_lesson(client):
    from app.db.models import StudySpace
    from app.teaching.lifecycle import pause_current_lesson

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    first = client.post(root + "/lessons", json={"idempotency_key": "first"}).json()
    with client.app.state.session_factory() as db:
        pause_current_lesson(db, db.get(StudySpace, sid), reason="pause", turn_id="pause")
        db.commit()
    second = client.post(root + "/lessons", json={"idempotency_key": "second"}).json()
    for i, q in enumerate(second["exercises"]):
        assert (
            client.post(
                root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": f"a{i}"}
            ).status_code
            == 201
        )
    client.post(root + f"/lessons/{second['id']}/complete", json={"idempotency_key": "read"})
    assert (
        client.post(root + f"/lessons/{first['id']}/resume", json={"idempotency_key": "resume"}).status_code
        == 200
    )
    assert client.get(root + "/lessons/current").json()["id"] == first["id"]

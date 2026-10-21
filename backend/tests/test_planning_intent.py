from conftest import provider, register, space


def test_focus_keeps_necessary_prerequisites():
    from app.planning.intent import effective_scope

    nodes = [
        {"key": "a", "prerequisites": []},
        {"key": "b", "prerequisites": ["a"]},
        {"key": "c", "prerequisites": []},
    ]
    result = effective_scope(nodes, {"included_concept_ids": ["b"], "deferred_concept_ids": ["a"]})
    assert set(result["included_ids"]) == {"a", "b"}
    assert result["explanations"]


def test_answer_replan_preserves_roadmap_and_preferences(client):
    from app.db.models import LearningIntent, StudySpace

    register(client)
    sid = space(client, provider(client))
    root = f"/api/v1/study-spaces/{sid}"
    with client.app.state.session_factory() as db:
        db.add(
            LearningIntent(
                space_id=sid,
                user_id=db.get(StudySpace, sid).user_id,
                version=1,
                data={
                    "teaching_preferences": "面试例子",
                    "stages": [{"title": "one", "concept_ids": ["os"]}],
                },
            )
        )
        db.commit()
    q = client.post(root + "/diagnostics").json()["items"][0]
    client.post(root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": "a"})
    plan = client.get(root + "/plan").json()
    assert plan["intent_version"] == 1
    assert plan["intent"]["teaching_preferences"] == "面试例子"
    assert plan["stages"][0]["title"] == "one"


def test_stage_assessment_obeys_priority_when_all_mastered():
    from datetime import UTC, datetime

    from app.planning.policy import choose_action

    nodes = [
        {"key": "os", "prerequisites": [], "importance": 3},
        {"key": "process", "prerequisites": ["os"], "importance": 2},
    ]
    states = {
        key: {"status": "mastered", "mastery_estimate": 0.95, "evidence_confidence": "high"}
        for key in ["os", "process"]
    }
    result = choose_action(
        nodes,
        states,
        {},
        [],
        30,
        now=datetime(2026, 1, 1, tzinfo=UTC),
        intent={"priority_concept_ids": ["process"]},
    )
    assert result["concept_ids"] == ["process"]
    assert result["action"] == "ASSESS"

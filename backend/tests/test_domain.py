import pytest
from pydantic import ValidationError

from app.learner.estimator import estimate
from app.planning.policy import choose_action
from app.schemas.domain import Curriculum, QuestionBatch


def concept(key, prerequisites=None):
    return {
        "key": key,
        "name": key,
        "module": "基础",
        "objectives": ["解释与应用"],
        "prerequisites": prerequisites or [],
        "importance": 1,
        "minutes": 15,
    }


@pytest.mark.parametrize(
    "nodes",
    [
        [concept("a"), concept("a")],
        [concept("a", ["missing"])],
        [concept("a", ["b"]), concept("b", ["a"])],
    ],
)
def test_rejects_invalid_graph(nodes):
    with pytest.raises(ValidationError):
        Curriculum(concepts=nodes)


def test_curriculum_source_is_always_unverified():
    curriculum = Curriculum(concepts=[concept("a"), concept("b", ["a"])])
    assert curriculum.concepts[0].source_status == "model_generated_unverified"
    with pytest.raises(ValidationError):
        Curriculum(concepts=[{**concept("a"), "source_status": "verified"}])


def evidence(
    item="q1", correct=True, assistance="none", concepts=None, confidence="high", kind="assessment_submitted"
):
    return {
        "type": kind,
        "assessment_item_id": item,
        "is_correct": correct,
        "assistance_level": assistance,
        "concept_ids": concepts or ["a"],
        "confidence": confidence,
        "difficulty": 2,
    }


def test_views_and_uncertain_scoring_never_imply_mastery():
    state = estimate("a", [evidence(kind="lesson_viewed"), evidence(confidence="low")])
    assert state["status"] == "unknown"
    assert state["mastery_estimate"] is None


def test_mastery_requires_distinct_independent_contexts():
    assert estimate("a", [evidence(), evidence()])["status"] == "learning"
    assert estimate("a", [evidence(), evidence("q2")])["status"] == "mastered"
    assert estimate("a", [evidence(), evidence("q2", assistance="hint")])["status"] == "learning"
    assert (
        estimate("a", [evidence(assistance="hint")])["mastery_estimate"]
        < estimate("a", [evidence()])["mastery_estimate"]
    )


def test_llm_only_grades_need_external_verification_before_mastery():
    events = [
        {**evidence("open1"), "evaluator": "llm_rubric:model"},
        {**evidence("open2"), "evaluator": "llm_rubric:model"},
    ]
    assert estimate("a", events)["status"] != "mastered"


def test_wrong_answer_and_multi_concept_attribution_are_conservative():
    mastered = [evidence(), evidence("q2")]
    assert estimate("a", mastered + [evidence("q3", correct=False)])["status"] == "learning"
    assert estimate("a", [evidence(correct=False, concepts=["a", "b"])])["status"] == "unknown"


def test_prerequisites_block_advanced_tasks_and_diagnosis_is_bounded():
    nodes = [concept("a"), concept("b", ["a"])]
    unknown = {"a": {"status": "unknown"}, "b": {"status": "unknown"}}
    assert choose_action(nodes, unknown, 0, 30)["action"] == "DIAGNOSE"
    action = choose_action(nodes, unknown, 5, 10)
    assert action["action"] == "LEARN_CONCEPT"
    assert action["concept_ids"] == ["a"]
    assert action["estimated_minutes"] <= 10
    assert choose_action(nodes, {"a": {"status": "mastered"}, "b": {"status": "learning"}}, 5, 30)[
        "concept_ids"
    ] == ["b"]


def test_question_answer_key_must_match_options():
    with pytest.raises(ValidationError):
        QuestionBatch(
            items=[
                {
                    "prompt": "问题",
                    "concept_keys": ["a"],
                    "kind": "choice",
                    "options": {"A": "一", "B": "二"},
                    "answer": "C",
                    "rubric": "解释",
                    "difficulty": 2,
                }
            ]
        )

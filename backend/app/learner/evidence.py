"""Normalize immutable answer events, never infer mastery from reading."""

from dataclasses import dataclass

ASSESSMENTS = {"diagnostic_submitted", "assessment_submitted", "review_submitted", "practice_completed"}


@dataclass(frozen=True)
class EvidenceBatch:
    observations: tuple[dict, ...]
    uncertain_count: int = 0
    composite_count: int = 0


def observations_for(concept_id: str, events: list[dict]) -> EvidenceBatch:
    observations, seen = [], set()
    uncertain = composite = 0
    ordered = sorted(
        events,
        key=lambda e: (e.get("occurred_at") or "", e.get("observation_order") or e.get("event_id") or ""),
    )
    hints = {e.get("assessment_item_id") for e in ordered if e["type"] == "hint_requested"}
    for raw in ordered:
        if raw["type"] not in ASSESSMENTS | {"exam_question_imported"} or concept_id not in raw.get(
            "concept_ids", []
        ):
            continue
        item = raw.get("assessment_item_id")
        if not item or item in seen:
            continue
        seen.add(item)
        if len(raw["concept_ids"]) != 1:
            composite += 1
            continue
        if (
            raw.get("confidence") != "high"
            or not isinstance(raw.get("is_correct"), bool)
            or raw.get("evaluator", "").startswith("llm_rubric:")
        ):
            uncertain += 1
            continue
        if raw["type"] == "exam_question_imported" and not (
            raw.get("evaluator") == "teacher_mark_extraction:v1"
            and raw.get("teacher_mark_clear") is True
            and bool(raw.get("teacher_marks"))
            and raw.get("recognition_confidence") == "high"
            and raw.get("mapping_confidence") == "high"
            and raw.get("teacher_result") == ("correct" if raw["is_correct"] else "incorrect")
            and raw.get("assistance_level") == "unknown"
            and raw.get("difficulty") == 1
        ):
            uncertain += 1
            continue
        assistance = raw.get("assistance_level", "none")
        if assistance == "solution":
            continue
        if item in hints and assistance == "none":
            assistance = "hint"
        observations.append({**raw, "assistance_level": assistance})
    return EvidenceBatch(tuple(observations), uncertain, composite)

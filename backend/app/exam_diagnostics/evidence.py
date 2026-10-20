from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo


def qualify(question):
    if question.result not in {"correct", "incorrect"}:
        return False, "非完整正确或错误，未生成二元掌握证据"
    if (
        not question.teacher_mark_clear
        or not question.teacher_marks.strip()
        or question.teacher_result != question.result
    ):
        return False, "缺少清晰一致的老师批改依据"
    if question.recognition_confidence != "high":
        return False, "批改识别置信度不足"
    if question.mapping_confidence != "high" or len(question.concept_ids) != 1:
        return False, "知识点映射不明确或为多知识综合题"
    return True, None


def assessment_time(exam_date, timezone, imported_at):
    if exam_date is None:
        return imported_at, "imported_unknown"
    stamp = datetime.combine(exam_date, time(12), tzinfo=ZoneInfo(timezone)).astimezone(UTC)
    return min(stamp, imported_at), "date"


def event_payload(diagnostic_id, question, imported_at, exam_date):
    return {
        "assessment_item_id": f"exam:{diagnostic_id}:{question.key}",
        "diagnostic_id": diagnostic_id,
        "question_key": question.key,
        "source_id": question.source_id,
        "concept_ids": question.concept_ids,
        "is_correct": question.result == "correct",
        "confidence": "high",
        "recognition_confidence": question.recognition_confidence,
        "mapping_confidence": question.mapping_confidence,
        "teacher_mark_clear": question.teacher_mark_clear,
        "teacher_result": question.teacher_result,
        "teacher_marks": question.teacher_marks,
        "evaluator": "teacher_mark_extraction:v1",
        "assistance_level": "unknown",
        "difficulty": 1,
        "evidence_policy": "evidence_v3_exam",
        "misconceptions": [],
        "imported_at": imported_at.isoformat(),
        "exam_date": str(exam_date) if exam_date else None,
        "assessment_time_source": "date" if exam_date else "imported_unknown",
        "observation_order": f"{diagnostic_id}:{question.leaf_order:04d}",
    }

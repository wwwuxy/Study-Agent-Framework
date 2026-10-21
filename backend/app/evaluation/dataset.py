import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def validate_dataset(dataset):
    seen = set()
    if not dataset.get("version") or not dataset.get("learners"):
        raise ValueError("缺少版本或学习序列")
    for learner in dataset["learners"]:
        if learner["learner_id"] in seen:
            raise ValueError("学习者重复或跨拟合／验证／测试划分泄漏")
        seen.add(learner["learner_id"])
        if learner["split"] not in {"train", "validation", "test"} or not learner["events"]:
            raise ValueError("学习序列划分无效")
        ids, previous = set(), None
        for event in learner["events"]:
            at = datetime.fromisoformat(event["at"])
            if not at.tzinfo or at.utcoffset() != UTC.utcoffset(at) or (previous and at <= previous):
                raise ValueError("事件必须按严格递增 UTC 时间排列")
            if (
                event["id"] in ids
                or not isinstance(event["correct"], bool)
                or event["assistance"] not in {"none", "hint"}
            ):
                raise ValueError("事件重复或观测类型无效")
            if event["rating"] not in {1, 2, 3, 4}:
                raise ValueError("FSRS 评分无效")
            if (not event["correct"] or event["assistance"] != "none") and event["rating"] != 1:
                raise ValueError("FSRS 评分与独立回忆证据不一致")
            ids.add(event["id"])
            previous = at
    return dataset


def load_dataset(path):
    path = Path(path)
    raw = path.read_bytes()
    manifest = json.loads(path.with_name("manifest.json").read_text())
    dataset = validate_dataset(json.loads(raw))
    if manifest["sha256"] != hashlib.sha256(raw).hexdigest() or manifest["version"] != dataset["version"]:
        raise ValueError("数据集版本或内容哈希不匹配")
    actual = {
        split: sorted(s["learner_id"] for s in dataset["learners"] if s["split"] == split)
        for split in ("train", "validation", "test")
    }
    if actual != manifest["splits"] or any(not rows for rows in actual.values()):
        raise ValueError("数据划分与清单不一致")
    return dataset


def observations(learner):
    return [
        {
            "type": "assessment_submitted",
            "event_id": e["id"],
            "assessment_item_id": e["id"],
            "concept_ids": ["skill"],
            "is_correct": e["correct"],
            "confidence": "high",
            "evaluator": "deterministic_answer_key",
            "assistance_level": e["assistance"],
            "difficulty": 2,
            "occurred_at": e["at"],
        }
        for e in learner["events"]
    ]


def review_logs(dataset, split="train"):
    result = []
    for learner in dataset["learners"]:
        if learner["split"] != split:
            continue
        card_id = int(hashlib.sha256(learner["learner_id"].encode()).hexdigest()[:13], 16)
        result.extend(
            {
                "card_id": card_id,
                "rating": e["rating"],
                "review_datetime": e["at"],
                "review_duration": e["duration_ms"],
            }
            for e in learner["events"]
        )
    return result

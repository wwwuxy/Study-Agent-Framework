import math
from datetime import datetime

from fsrs import Card, Rating
from pyBKT.fit import predict_onestep

from app.evaluation.dataset import observations, validate_dataset
from app.learner.bkt import native_data, native_model
from app.learner.parameters import ParameterBundle, validate_parameter_artifact
from app.reviews.fsrs_adapter import scheduler


def summary(rows):
    if not rows:
        return {
            "count": 0,
            "brier_score": None,
            "log_loss": None,
            "error_rate": None,
            "reason": "没有合格的预测观测",
            "confusion": {"tp": 0, "tn": 0, "fp": 0, "fn": 0},
        }
    n = len(rows)
    confusion = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    for row in rows:
        predicted, correct = row["probability"] >= 0.5, row["correct"]
        confusion["tp" if predicted and correct else "fp" if predicted else "fn" if correct else "tn"] += 1
    return {
        "count": n,
        "brier_score": sum((r["probability"] - r["correct"]) ** 2 for r in rows) / n,
        "log_loss": -sum(
            math.log(max(1e-12, min(1 - 1e-12, r["probability"] if r["correct"] else 1 - r["probability"])))
            for r in rows
        )
        / n,
        "error_rate": (confusion["fp"] + confusion["fn"]) / n,
        "confusion": confusion,
    }


def evaluate(dataset, parameters=None, split="test"):
    validate_dataset(dataset)
    bundle = validate_parameter_artifact(parameters) if parameters else ParameterBundle()
    rows, memory_rows = [], []
    native_scheduler = scheduler(bundle.fsrs)
    for learner in dataset["learners"]:
        if learner["split"] != split:
            continue
        obs = observations(learner)
        predictions, _ = predict_onestep.run(native_model(bundle.bkt), native_data(obs), parallel=False)
        card = Card(card_id=1, due=datetime.fromisoformat(learner["events"][0]["at"]))
        for index, event in enumerate(learner["events"]):
            rows.append(
                {
                    "learner_id": learner["learner_id"],
                    "event_id": event["id"],
                    "probability": float(predictions[index]),
                    "correct": event["correct"],
                    "assistance": event["assistance"],
                }
            )
            at = datetime.fromisoformat(event["at"])
            if card.last_review and (at - card.last_review).days > 0:
                memory_rows.append(
                    {
                        "probability": native_scheduler.get_card_retrievability(card, at),
                        "correct": event["rating"] != 1,
                    }
                )
            card, _ = native_scheduler.review_card(card, Rating(event["rating"]), at, event["duration_ms"])
    return {
        "data_version": dataset["version"],
        "split": split,
        **summary(rows),
        "by_mode": {mode: summary([r for r in rows if r["assistance"] == mode]) for mode in ("none", "hint")},
        "fsrs": summary(memory_rows),
        "predictions": rows,
        "notice": "自有合成数据评测不证明真实教育效果；预测先于当前观测更新。",
    }

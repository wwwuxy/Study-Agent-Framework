from datetime import datetime
from importlib.metadata import version

import numpy as np
from pyBKT.fit import EM_fit
from pyBKT.generate import random_model_uni

from app.evaluation.dataset import observations, validate_dataset
from app.evaluation.metrics import evaluate
from app.learner.bkt import native_data
from app.learner.parameters import BKTParameters, FSRSParameters, ParameterBundle


def artifact(bundle, data_version):
    return {
        "artifact_version": "learner-parameters-v1",
        "status": "candidate",
        "libraries": {"pyBKT": version("pyBKT"), "fsrs": version("fsrs")},
        "data_version": data_version,
        **bundle.model_dump(mode="json"),
    }


def fit_bkt(dataset, seed=42):
    validate_dataset(dataset)
    learners = [s for s in dataset["learners"] if s["split"] == "train"]
    obs = [observations(s) for s in learners]
    if len(obs) < 10 or sum(map(len, obs)) < 100 or len({e["is_correct"] for seq in obs for e in seq}) < 2:
        raise ValueError("BKT 拟合数据不足：至少 10 条学习者序列、100 次作答及两种结果")
    lengths = np.array([len(seq) for seq in obs])
    data = {
        "data": np.concatenate([native_data(seq)["data"][:, :-1] for seq in obs], axis=1),
        "starts": np.cumsum(np.r_[1, lengths[:-1]]),
        "lengths": lengths,
        "resources": np.ones(sum(lengths), dtype=np.int64),
    }
    candidates = []
    for initialization in range(3):
        model = random_model_uni.random_model_uni(1, 2, rand=np.random.RandomState(seed + initialization))
        fitted, likelihood = EM_fit.EM_fit(model, data, parallel=False, fixed={"forgets": np.array([0.0])})
        try:
            params = BKTParameters(
                version=f"bkt-fit-{dataset['version']}-{seed}",
                prior=float(fitted["prior"]),
                learn=float(fitted["learns"][0]),
                guess=float(fitted["guesses"][0]),
                slip=float(fitted["slips"][0]),
                hint_guess=float(fitted["guesses"][1]),
                hint_slip=float(fitted["slips"][1]),
            )
        except ValueError:
            continue
        candidate = artifact(
            ParameterBundle(bkt=params, calibration_status="synthetic_only"), dataset["version"]
        )
        candidate["training_log_likelihood"] = float(likelihood[-1, 0])
        candidate["validation"] = evaluate(dataset, candidate, split="validation")
        if candidate["validation"]["log_loss"] is not None:
            candidates.append(candidate)
    if not candidates:
        raise ValueError("拟合结果不可辨识或验证数据不足；保持默认参数")
    best = min(candidates, key=lambda c: c["validation"]["log_loss"])
    best["test"] = evaluate(dataset, best)
    return best


def optimize_fsrs(logs, *, optimize_retention=False):
    grouped, delayed = {}, 0
    for row in sorted(logs, key=lambda r: (r["card_id"], r["review_datetime"])):
        at = datetime.fromisoformat(row["review_datetime"])
        previous = grouped.get(row["card_id"])
        if previous and (at - previous).days > 0:
            delayed += 1
        grouped[row["card_id"]] = at
    if delayed < 512 or len({r["rating"] == 1 for r in logs}) < 2:
        raise ValueError("FSRS 优化数据不足：至少 512 次跨日复习，且包含成功与失败")
    from fsrs import Optimizer, ReviewLog

    optimizer = Optimizer([ReviewLog.from_dict(r) for r in logs])
    weights = optimizer.compute_optimal_parameters()
    retention = float(optimizer.compute_optimal_retention(weights)) if optimize_retention else 0.9
    params = FSRSParameters(version="fsrs-fit-v1", parameters=tuple(weights), desired_retention=retention)
    return {
        "fsrs": params.model_dump(mode="json"),
        "delayed_reviews": delayed,
        "retention_optimized": optimize_retention,
    }

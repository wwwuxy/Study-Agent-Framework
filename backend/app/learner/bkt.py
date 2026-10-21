"""pyBKT's native forward inference, with conservative application labels."""

import hashlib
import json
import math

import numpy as np
from pyBKT.fit import predict_onestep

from app.learner.evidence import EvidenceBatch
from app.learner.parameters import BKTParameters


def native_model(params: BKTParameters):
    return {
        "prior": params.prior,
        "learns": np.array([params.learn]),
        "forgets": np.array([0.0]),
        "guesses": np.array([params.guess, params.hint_guess]),
        "slips": np.array([params.slip, params.hint_slip]),
    }


def native_data(observations):
    # The final unobserved checkpoint reads the library's next latent state.
    matrix = np.zeros((2, len(observations) + 1), dtype=np.int32)
    for index, item in enumerate(observations):
        row = int(item.get("assistance_level") != "none")
        matrix[row, index] = 2 if item["is_correct"] else 1
    return {
        "data": matrix,
        "resources": np.ones(matrix.shape[1], dtype=np.int64),
        "starts": np.array([1]),
        "lengths": np.array([matrix.shape[1]]),
    }


def estimate_bkt(batch: EvidenceBatch, params: BKTParameters) -> dict:
    values = batch.observations
    p = None
    if values:
        _, states = predict_onestep.run(native_model(params), native_data(values), parallel=False)
        p = float(states[1, -1])
        if not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError("pyBKT 返回了无效概率；状态未更新")
    independent = sum(
        e["is_correct"] and e["assistance_level"] == "none" and e.get("difficulty", 0) >= 2 for e in values
    )
    status = "unknown" if not values else "learning"
    if independent >= 2 and p >= 0.8 and values[-1]["is_correct"]:
        status = "mastered"
    return {
        "status": status,
        "mastery_estimate": p,
        "evidence_count": len(values),
        "independent_correct_count": independent,
        "assisted_count": sum(e["assistance_level"] != "none" for e in values),
        "uncertain_count": batch.uncertain_count,
        "composite_count": batch.composite_count,
        "evidence_confidence": "high" if len(values) >= 4 else "medium" if len(values) >= 2 else "low",
        "misconceptions": list(dict.fromkeys(m for e in values[-5:] for m in e.get("misconceptions", []))),
        "recent_error": bool(values and not values[-1]["is_correct"]),
        "estimator_version": "pybkt_v1",
        "parameter_version": params.version,
        "evidence_policy": "evidence_v3_exam"
        if any(e["type"] == "exam_question_imported" for e in values)
        else "evidence_v2",
        "last_assessment_time_source": values[-1].get("assessment_time_source", "observed")
        if values
        else None,
        "calibration_status": "uncalibrated",
        "last_assessed_at": values[-1].get("occurred_at") if values else None,
        "evidence_window": {
            "count": len(values),
            "start": values[0].get("occurred_at") if values else None,
            "end": values[-1].get("occurred_at") if values else None,
            "sha256": hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest(),
        },
    }

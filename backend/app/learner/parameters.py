"""Versioned, immutable configuration for the two mandatory algorithms."""

import json
from importlib.metadata import version
from pathlib import Path

from fsrs import Scheduler
from fsrs.scheduler import DEFAULT_PARAMETERS
from pydantic import BaseModel, ConfigDict, Field, model_validator


class BKTParameters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    version: str = "bkt-defaults-v1"
    prior: float = Field(default=0.2, gt=0, lt=1)
    learn: float = Field(default=0.1, ge=0, lt=1)
    guess: float = Field(default=0.25, gt=0, lt=1)
    slip: float = Field(default=0.1, gt=0, lt=1)
    hint_guess: float = Field(default=0.75, gt=0, lt=1)
    hint_slip: float = Field(default=0.05, gt=0, lt=1)

    @model_validator(mode="after")
    def identifiable(self):
        if self.guess + self.slip >= 1 or self.hint_guess + self.hint_slip >= 1:
            raise ValueError("BKT 观测类别无法区分掌握与未掌握")
        return self


class FSRSParameters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    version: str = "fsrs-defaults-v1"
    parameters: tuple[float, ...] = DEFAULT_PARAMETERS
    desired_retention: float = Field(default=0.9, gt=0, lt=1)

    @model_validator(mode="after")
    def valid_scheduler(self):
        Scheduler(parameters=self.parameters, desired_retention=self.desired_retention, enable_fuzzing=False)
        return self


class ParameterBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    bkt: BKTParameters = Field(default_factory=BKTParameters)
    fsrs: FSRSParameters = Field(default_factory=FSRSParameters)
    calibration_status: str = "uncalibrated"


def validate_parameter_artifact(artifact):
    if artifact.get("artifact_version") != "learner-parameters-v1" or artifact.get("status") not in {
        "candidate",
        "validated",
    }:
        raise ValueError("参数产物格式或状态无效")
    libs = artifact.get("libraries", {})
    if libs != {"pyBKT": version("pyBKT"), "fsrs": version("fsrs")}:
        raise ValueError("参数产物与当前算法库版本不一致")
    return ParameterBundle(
        bkt=artifact["bkt"],
        fsrs=artifact["fsrs"],
        calibration_status=artifact.get("calibration_status", "uncalibrated"),
    )


def load_parameter_bundle(path=None):
    if not path:
        return ParameterBundle()
    artifact = json.loads(Path(path).read_text())
    bundle = validate_parameter_artifact(artifact)
    if artifact["status"] != "validated":
        raise ValueError("候选参数不能直接用于在线服务，请先评测并验证")
    return bundle


def algorithm_manifest(bundle=None):
    bundle = bundle or ParameterBundle()
    return {
        "bkt": {
            "enabled": True,
            "implementation": "pyBKT",
            "library_version": version("pyBKT"),
            "algorithm_version": "pybkt_v1",
            "parameter_version": bundle.bkt.version,
        },
        "fsrs": {
            "enabled": True,
            "implementation": "py-fsrs",
            "library_version": version("fsrs"),
            "algorithm_version": "fsrs_v6",
            "parameter_version": bundle.fsrs.version,
        },
        "evidence_policy": "evidence_v2",
        "calibration_status": bundle.calibration_status,
        "notice": "掌握评估与复习安排会随作答记录更新。当前使用默认参数，尚未针对个人校准，估计结果仅供学习参考。",
    }

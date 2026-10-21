import argparse
import json
from pathlib import Path

from app.evaluation.calibration import artifact, fit_bkt, optimize_fsrs
from app.evaluation.dataset import load_dataset, review_logs
from app.evaluation.metrics import evaluate
from app.learner.parameters import FSRSParameters, ParameterBundle, validate_parameter_artifact


def main():
    parser = argparse.ArgumentParser(description="无网络、无用户数据库读取的算法评测与校准")
    parser.add_argument("command", choices=["evaluate", "fit-bkt", "optimize-fsrs", "validate"])
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parameters", type=Path)
    parser.add_argument("--optimize-retention", action="store_true")
    args = parser.parse_args()
    try:
        dataset = load_dataset(args.dataset)
        params = json.loads(args.parameters.read_text()) if args.parameters else None
        if args.command == "evaluate":
            result = evaluate(dataset, params)
        elif args.command == "fit-bkt":
            result = fit_bkt(dataset)
        elif args.command == "optimize-fsrs":
            optimized = optimize_fsrs(review_logs(dataset), optimize_retention=args.optimize_retention)
            result = artifact(
                ParameterBundle(
                    fsrs=FSRSParameters(**optimized["fsrs"]), calibration_status="synthetic_only"
                ),
                dataset["version"],
            )
            result.update({k: v for k, v in optimized.items() if k != "fsrs"})
            result["validation"], result["test"] = (
                evaluate(dataset, result, "validation"),
                evaluate(dataset, result),
            )
        else:
            if not params or params.get("data_version") != dataset["version"]:
                raise ValueError("必须指定属于当前数据集的候选参数")
            validate_parameter_artifact(params)
            if not params.get("validation") or not params.get("test"):
                raise ValueError("缺少独立验证／测试指标，不能发布")
            result = {**params, "status": "validated"}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "status": result.get("status", "evaluated"),
                    "data_version": dataset["version"],
                },
                ensure_ascii=False,
            )
        )
    except (ValueError, KeyError, ImportError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()

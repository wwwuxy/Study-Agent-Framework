import argparse
import asyncio
import json

from app.core.settings import Settings
from app.maintenance.reset_learning import reset_learning


def main():
    parser = argparse.ArgumentParser(description="StudyAgent 本机维护；默认只读预览")
    sub = parser.add_subparsers(dest="command", required=True)
    reset = sub.add_parser("reset-learning")
    reset.add_argument("--operation-id", required=True)
    reset.add_argument("--apply", action="store_true")
    reset.add_argument("--expected-target")
    rebuild = sub.add_parser("rebuild-algorithms")
    rebuild.add_argument("--operation-id", required=True)
    rebuild.add_argument("--artifact", required=True)
    args = parser.parse_args()
    try:
        if args.command == "rebuild-algorithms":
            from pathlib import Path

            from app.maintenance.rebuild_algorithms import rebuild_algorithms

            result = asyncio.run(
                rebuild_algorithms(Settings(), json.loads(Path(args.artifact).read_text()), args.operation_id)
            )
        else:
            result = asyncio.run(
                reset_learning(
                    Settings(), args.operation_id, apply=args.apply, expected_target=args.expected_target
                )
            )
    except (ValueError, BlockingIOError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run against a disposable local pgserver by default.
An existing TEST_DATABASE_URL is used only with --use-test-database.

No downloads and no access to the configured learning database. pgserver is an
optional local verification dependency, not required by the application.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(env):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests", "-q"],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--use-test-database",
        action="store_true",
        help="Explicitly use TEST_DATABASE_URL (tests create/drop isolated schemas)",
    )
    args = parser.parse_args()
    env = os.environ.copy()
    if args.use_test_database:
        if not env.get("TEST_DATABASE_URL"):
            parser.error("TEST_DATABASE_URL is required")
        return run(env)
    env.pop("TEST_DATABASE_URL", None)
    try:
        import pgserver
        from pgserver.postgres_server import PostgresServer
    except ImportError:
        print(
            "Set TEST_DATABASE_URL to an isolated PostgreSQL test database, or install optional pgserver.",
            file=sys.stderr,
        )
        return 2
    with tempfile.TemporaryDirectory(prefix="study-agent-pg-") as directory:
        root = Path(directory)
        PostgresServer.runtime_path = root / "runtime"
        PostgresServer.runtime_path.mkdir()
        PostgresServer.lock_path = root / "runtime" / ".lockfile"
        PostgresServer._lock = PostgresServer.fasteners.InterProcessLock(
            PostgresServer.lock_path
        )
        with pgserver.get_server(root / "database", cleanup_mode="delete") as server:
            env["TEST_DATABASE_URL"] = server.get_uri().replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
            return run(env)


if __name__ == "__main__":
    raise SystemExit(main())

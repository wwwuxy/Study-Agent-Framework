#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
bash -n scripts/setup.sh scripts/serve.sh scripts/dev.sh
.venv/bin/pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build

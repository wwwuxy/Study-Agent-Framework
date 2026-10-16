#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/study-agent ] || [ ! -f .env ]; then
  ./scripts/setup.sh --backend-only
fi
mkdir -p data
.venv/bin/alembic -c backend/alembic.ini upgrade head
exec .venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${STUDY_AGENT_PORT:-8000}"

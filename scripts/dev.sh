#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -f .env ] || [ ! -d frontend/node_modules ]; then
  ./scripts/setup.sh
fi
mkdir -p data
.venv/bin/alembic -c backend/alembic.ini upgrade head
.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 &
backend_pid=$!
cleanup() { kill "$backend_pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
npm --prefix frontend run dev

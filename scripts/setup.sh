#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
backend_only=false
if [ "$#" -gt 0 ]; then
  if [ "$#" -eq 1 ] && [ "$1" = "--backend-only" ]; then
    backend_only=true
  else
    printf 'Usage: %s [--backend-only]\n' "$0" >&2
    exit 2
  fi
fi
export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/study-agent-uv}"
if [ ! -x .venv/bin/python ]; then
  uv venv --python "${PYTHON_BIN:-python3.12}" .venv
fi
uv pip install --python .venv/bin/python -r backend/requirements-dev.lock -e './backend[dev]'
if [ ! -f .env ]; then
  .venv/bin/python - <<'PY'
import os
import secrets
from pathlib import Path
from cryptography.fernet import Fernet
text = Path('.env.example').read_text()
text = text.replace('CREDENTIAL_ENCRYPTION_KEY=\n', 'CREDENTIAL_ENCRYPTION_KEY=' + Fernet.generate_key().decode() + '\n')
text = text.replace('COOKIE_SECURE=true', 'COOKIE_SECURE=false')
text = text.replace('POSTGRES_PASSWORD=\n', 'POSTGRES_PASSWORD=' + secrets.token_urlsafe(32) + '\n')
Path('.env').write_text(text)
os.chmod('.env', 0o600)
print('Created .env for local HTTP development; demo stays off unless explicitly enabled.')
PY
fi
mkdir -p data
.venv/bin/alembic -c backend/alembic.ini upgrade head
if [ "$backend_only" = false ]; then
  npm --prefix frontend ci --cache "${STUDY_AGENT_NPM_CACHE:-${TMPDIR:-/tmp}/study-agent-npm}" --no-audit --no-fund
  npm --prefix frontend run build
fi
printf '\nReady. CLI: source .venv/bin/activate && study-agent --help\nBackend: ./scripts/serve.sh\nWeb: ./scripts/dev.sh\n'

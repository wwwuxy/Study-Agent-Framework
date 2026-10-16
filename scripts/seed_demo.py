"""Create an explicitly requested, local-only demo account and learning space.
Run: ENABLE_FAKE_PROVIDER=true .venv/bin/python scripts/seed_demo.py
"""

import os
import secrets
from pathlib import Path

from app.core.settings import Settings
from app.main import create_app
from fastapi.testclient import TestClient

settings = Settings()
if not settings.enable_fake_provider:
    raise SystemExit("Refusing to seed: explicitly set ENABLE_FAKE_PROVIDER=true.")
settings.cookie_secure = False
username = os.environ.get("DEMO_USERNAME", "demo")
password = os.environ.get("DEMO_PASSWORD", secrets.token_urlsafe(18))
with TestClient(create_app(settings)) as client:
    result = client.post(
        "/api/v1/auth/register", json={"username": username, "password": password}
    )
    if result.status_code == 409:
        result = client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
    if result.status_code not in (200, 201):
        raise SystemExit(
            "Demo account exists; pass its original DEMO_PASSWORD or a new DEMO_USERNAME."
        )
    configs = client.get("/api/v1/providers").json()
    config = next((p for p in configs if p["provider_type"] == "fake"), None)
    if not config:
        result = client.post(
            "/api/v1/providers",
            json={
                "name": "操作系统 · 离线演示",
                "provider_type": "fake",
                "chat_model": "demo-model",
                "api_key": "demo",
            },
        )
        result.raise_for_status()
        config = result.json()
    client.post("/api/v1/providers/" + config["id"] + "/test").raise_for_status()
    result = client.post(
        "/api/v1/study-spaces",
        json={
            "provider_id": config["id"],
            "goal": "系统学习操作系统",
            "daily_minutes": 30,
            "idempotency_key": "demo-os-space",
        },
    )
    result.raise_for_status()
    sid = result.json()["id"]
    result = client.post(f"/api/v1/study-spaces/{sid}/diagnostics")
    result.raise_for_status()
    items = result.json()["items"]
    for i, item in enumerate(items):
        # Preserve a weak foundation so the first recommended lesson is meaningful.
        result = client.post(
            f"/api/v1/study-spaces/{sid}/attempts",
            json={
                "item_id": item["id"],
                "answer": "B" if item["concept_keys"] == ["os"] else "A",
                "idempotency_key": f"demo-diag-{i}",
            },
        )
        result.raise_for_status()
access = Path("data/demo-access.txt")
access.parent.mkdir(exist_ok=True)
access.write_text(
    f"Local demo only\nURL: http://localhost:8000\nUsername: {username}\nPassword: {password}\n"
)
access.chmod(0o600)
print(
    "Demo ready. Login details saved to data/demo-access.txt (local, gitignored, mode 0600)."
)

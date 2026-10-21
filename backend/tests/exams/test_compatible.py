import asyncio
import base64
import json

import httpx

from app.db.models import ProviderConfig
from app.exam_diagnostics.worker import tick
from app.providers.compatible import CompatibleAdapter

from .test_uploads import create, put


def test_compatible_image_probe_enables_upload_and_real_worker_protocol(
    exam_env, image_bytes, recognition_payload, monkeypatch
):
    marker = "ac135709bdef2468"

    async def resolver(host, port):
        return ["8.8.8.8"]

    def handle(request):
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert "thinking" not in body
        content = body["messages"][-1]["content"]
        if isinstance(content, list):
            task = json.loads(content[-1]["text"])
            if "marker" in task["schema"]["properties"]:
                result = {"marker": marker}
            else:
                image = next(c["image_url"]["url"] for c in content if c["type"] == "image_url")
                assert base64.b64decode(image.split(",", 1)[1]) == image_bytes
                assert content[0]["text"] == "附件标识：a1"
                result = recognition_payload
        elif (
            "JSON Schema" in body["messages"][0]["content"] and "ExamAdvice" in body["messages"][0]["content"]
        ):
            result = {"summary": "根据老师批改整理的诊断", "suggestions": []}
        else:
            result = {"ok": True}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(result)}, "finish_reason": "stop"}],
            },
        )

    exam_env.app.state.adapter_factory = lambda config: CompatibleAdapter(
        "https://example.com/v1",
        "test-key",
        "agnes-2.5-flash",
        transport=httpx.MockTransport(handle),
        resolver=resolver,
        retries=0,
    )
    with exam_env.app.state.session_factory.begin() as db:
        config = db.get(ProviderConfig, exam_env.provider_id)
        config.provider_type = "openai_compatible"
        config.tested, config.capabilities = False, {}
    with monkeypatch.context() as patch:
        patch.setattr("secrets.token_hex", lambda n: marker)
        tested = exam_env.client.post(f"/api/v1/providers/{exam_env.provider_id}/test")
    assert tested.status_code == 200, tested.text
    caps = exam_env.client.get(exam_env.root + "/capabilities").json()
    assert caps["images"] == ["image/png", "image/jpeg"] and caps["pdf"] is False
    row = create(exam_env, image_bytes, "paper.png", "image/png")
    assert put(exam_env, row, image_bytes, "image/png").status_code == 200
    started = exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start",
        json={"consent": True, "idempotency_key": "compatible-image"},
    )
    assert started.status_code == 202, started.text
    asyncio.run(tick(exam_env.app))
    report = exam_env.client.get(exam_env.root + "/" + row["id"]).json()
    assert report["status"] == "completed", report
    assert report["effective_evidence_count"] == 2

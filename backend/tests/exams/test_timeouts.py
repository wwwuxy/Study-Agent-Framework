import asyncio
import json

import httpx

from app.exam_diagnostics.worker import tick
from app.providers.compatible import CompatibleAdapter

from .test_uploads import create, put


def test_exam_stages_use_exam_timeout_and_deepseek_extraction_mode(
    exam_env, image_bytes, recognition_payload
):
    requests = []

    def handle(request):
        requests.append(request)
        assert request.extensions["timeout"]["read"] == 120
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        content = body["messages"][-1]["content"]
        result = recognition_payload if isinstance(content, list) else {"summary": "test", "suggestions": []}
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(result)}, "finish_reason": "stop"}]}
        )

    async def resolver(host, port):
        return ["8.8.8.8"]

    exam_env.app.state.adapter_factory = lambda cfg: CompatibleAdapter(
        "https://api.deepseek.com",
        "test",
        "deepseek-flash",
        timeout=30,
        transport=httpx.MockTransport(handle),
        resolver=resolver,
        retries=0,
    )
    row = create(exam_env, image_bytes, "paper.png", "image/png")
    put(exam_env, row, image_bytes, "image/png")
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "start"}
    )
    asyncio.run(tick(exam_env.app))
    report = exam_env.client.get(exam_env.root + "/" + row["id"]).json()
    assert report["status"] == "completed", report.get("task")
    assert len(requests) == 2

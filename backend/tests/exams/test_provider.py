import base64
import json

import httpx
import pytest

from app.providers.base import ExamInput
from app.providers.native import NativeFileAdapter


@pytest.mark.asyncio
async def test_exam_uses_configured_model_and_ordered_original_inputs(image_bytes):
    async def resolver(host, port):
        return ["8.8.8.8"]

    def handle(request):
        body = json.loads(request.content)
        assert body["model"] == "user-model" and body["store"] is False
        content = body["input"][0]["content"]
        assert content[1]["file_id"] == "file-owned"
        assert content[3]["image_url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"content": [{"type": "output_text", "text": '{"ok":true}'}]}],
            },
        )

    adapter = NativeFileAdapter(
        "https://example.com/v1",
        "key",
        "user-model",
        resolver=resolver,
        transport=httpx.MockTransport(handle),
    )
    result = await adapter.analyze_exam(
        [
            ExamInput("a", "application/pdf", file_ref="file-owned"),
            ExamInput(
                "b", "image/png", data_url="data:image/png;base64," + base64.b64encode(image_bytes).decode()
            ),
        ],
        {"schema": {"type": "object"}},
        max_output_tokens=2000,
    )
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_images_require_independent_random_probe(monkeypatch):
    adapter = NativeFileAdapter("https://example.com/v1", "key", "model")
    seen = []

    async def image_response(inputs, task, **kw):
        assert "marker_value" not in task
        seen.append(inputs[0].mime_type)
        return {"marker": "wrong"}

    monkeypatch.setattr(adapter, "analyze_exam", image_response)
    caps = {}
    await adapter.probe_images(caps)
    assert caps["image_input"] is False
    assert caps["supported_image_mime_types"] == []
    assert seen == ["image/png", "image/jpeg"]

import json

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.native import NativeFileAdapter


@pytest.mark.asyncio
async def test_native_files_uses_pinned_upload_responses_delete_and_remote_embedding():
    requests = []

    def handle(request):
        requests.append(request)
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "example.com"
        if request.method == "DELETE":
            return httpx.Response(200, json={"deleted": True})
        if request.url.path.endswith("/files"):
            assert b"user_data" in request.content and b"%PDF-" in request.content
            return httpx.Response(200, json={"id": "file-owned"})
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]})
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["input"][0]["content"][0]["file_id"] == "file-owned"
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": '{"ok":true}'}]}]}
        )

    async def resolver(host, port):
        return ["8.8.8.8"]

    adapter = NativeFileAdapter(
        "https://example.com/v1",
        "secret",
        "user-model",
        embedding_model="user-embedding",
        resolver=resolver,
        transport=httpx.MockTransport(handle),
    )
    ref = await adapter.upload_file(b"%PDF-test", "safe.pdf")
    assert await adapter.analyze_file(ref, {"schema": {"type": "object"}}) == {"ok": True}
    assert await adapter.embed_texts(["hello"]) == [[1.0, 2.0]]
    await adapter.delete_file(ref)
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_embedding_rejects_non_finite_and_wrong_batch():
    async def resolver(host, port):
        return ["8.8.8.8"]

    adapter = NativeFileAdapter(
        "https://example.com/v1",
        "secret",
        "model",
        embedding_model="embed",
        resolver=resolver,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": []})),
    )
    with pytest.raises(ProviderError, match="向量"):
        await adapter.embed_texts(["hello"])


@pytest.mark.asyncio
@pytest.mark.parametrize("read_correctly", [True, False])
async def test_file_probe_requires_actual_random_content_and_cleans_up(read_correctly):
    import re

    marker = None
    deleted = []

    def handle(request):
        nonlocal marker
        if request.method == "DELETE":
            deleted.append(str(request.url))
            return httpx.Response(200, json={"deleted": True})
        if request.url.path.endswith("/files"):
            # This is the framework-owned test fixture, never user document extraction.
            marker = re.search(rb"\(([a-f0-9]{32})\) Tj", request.content).group(1).decode()
            return httpx.Response(200, json={"id": "file-probe"})
        if request.url.path.endswith("/responses"):
            body = json.loads(request.content)
            assert marker not in json.dumps(body)
            result = json.dumps({"marker": marker if read_correctly else "invented"})
            return httpx.Response(
                200, json={"output": [{"content": [{"type": "output_text", "text": result}]}]}
            )
        body = json.loads(request.content)
        text = '{"ok":true}' if any("JSON Schema" in m["content"] for m in body["messages"]) else "OK"
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    async def resolver(host, port):
        return ["8.8.8.8"]

    adapter = NativeFileAdapter(
        "https://example.com/v1", "secret", "model", transport=httpx.MockTransport(handle), resolver=resolver
    )
    caps = await adapter.probe_capabilities()
    assert caps["chat"] is True and caps["file_input"] is read_correctly
    assert caps["supported_mime_types"] == (["application/pdf"] if read_correctly else [])
    assert len(deleted) == 1 and caps["locator_verified"] is False

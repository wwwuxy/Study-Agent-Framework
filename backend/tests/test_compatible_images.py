import base64
import json

import httpx
import pytest

from app.providers.base import CapabilityNotSupported, ExamInput, ProviderError
from app.providers.compatible import CompatibleAdapter
from app.providers.probe_image import make_probe_image


def adapter(handler):
    async def resolver(host, port):
        return ["8.8.8.8"]

    return CompatibleAdapter(
        "https://example.com/v1",
        "secret",
        "agnes-2.5-flash",
        resolver=resolver,
        transport=httpx.MockTransport(handler),
        retries=0,
    )


async def test_compatible_images_preserve_order_model_budget_and_validate_json():
    png = make_probe_image("first", "image/png")
    jpeg = make_probe_image("second", "image/jpeg")

    def handle(request):
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "agnes-2.5-flash"
        assert body["max_tokens"] == 2000
        content = body["messages"][-1]["content"]
        assert content[0] == {"type": "text", "text": "附件标识：a"}
        assert content[1] == {"type": "image_url", "image_url": {"url": png}}
        assert content[2] == {"type": "text", "text": "附件标识：b"}
        assert content[3] == {"type": "image_url", "image_url": {"url": jpeg}}
        assert "低信任" in body["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    provider = adapter(handle)
    result = await provider.analyze_exam(
        [ExamInput("a", "image/png", data_url=png), ExamInput("b", "image/jpeg", data_url=jpeg)],
        {"schema": {"type": "object", "required": ["ok"], "properties": {"ok": {"const": True}}}},
        max_output_tokens=2000,
    )
    assert result == {"ok": True}
    assert provider.usage["prompt_tokens"] == 12


async def test_compatible_image_accepts_fenced_json_without_skipping_validation():
    provider = adapter(
        lambda _: httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '\n\n```json\n{"ok":true}\n```'}, "finish_reason": "stop"}
                ]
            },
        )
    )
    result = await provider.analyze_exam(
        [ExamInput("a", "image/png", data_url=make_probe_image("probe", "image/png"))],
        {"schema": {"type": "object", "properties": {"ok": {"const": True}}, "required": ["ok"]}},
        max_output_tokens=256,
    )
    assert result == {"ok": True}


@pytest.mark.parametrize(
    "text,finish", [('{"ok":false}', "stop"), ('{"ok":true}', "length"), ("invalid", "stop")]
)
async def test_compatible_image_results_reject_invalid_or_truncated_output(text, finish):
    provider = adapter(
        lambda _: httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": text}, "finish_reason": finish}],
            },
        )
    )
    with pytest.raises(ProviderError) as error:
        await provider.analyze_exam(
            [ExamInput("a", "image/png", data_url=make_probe_image("x", "image/png"))],
            {"schema": {"type": "object", "properties": {"ok": {"const": True}}, "required": ["ok"]}},
            max_output_tokens=256,
        )
    assert error.value.code == (
        "invalid_provider_response" if finish == "length" else "invalid_structured_output"
    )


@pytest.mark.parametrize(
    "item",
    [
        ExamInput("a", "application/pdf", file_ref="file-a"),
        ExamInput("a", "image/png", data_url="https://private.invalid/image.png"),
        ExamInput("a", "image/png", data_url="data:image/jpeg;base64,AAAA"),
    ],
)
async def test_compatible_images_reject_unsupported_inputs_before_sending(item):
    def unexpected(request):
        pytest.fail("unsupported input must not be sent")

    with pytest.raises(CapabilityNotSupported):
        await adapter(unexpected).analyze_exam([item], {"schema": {}}, max_output_tokens=256)


@pytest.mark.parametrize(
    "png_result,jpeg_result", [("correct", "correct"), ("correct", "rejected"), ("wrong", "timeout")]
)
async def test_compatible_probe_reads_random_images_and_keeps_chat_when_images_fail(
    monkeypatch, png_result, jpeg_result
):
    # The marker is only in the generated image, never in the text instruction.
    marker = "a319e047bc825fd6"
    monkeypatch.setattr("secrets.token_hex", lambda n: marker)
    seen = []

    def handle(request):
        body = json.loads(request.content)
        content = body["messages"][-1]["content"]
        if isinstance(content, str):
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})
        assert marker not in json.dumps(body)
        url = next(c["image_url"]["url"] for c in content if c["type"] == "image_url")
        mime = url.split(";")[0][5:]
        assert base64.b64decode(url.split(",", 1)[1]).startswith(
            b"\x89PNG" if mime == "image/png" else b"\xff\xd8"
        )
        seen.append(mime)
        outcome = png_result if mime == "image/png" else jpeg_result
        if outcome == "rejected":
            return httpx.Response(400, text="secret upstream response")
        if outcome == "timeout":
            raise httpx.ReadTimeout("secret timeout")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"marker": marker if outcome == "correct" else "invented"})
                        }
                    }
                ]
            },
        )

    caps = await adapter(handle).probe_capabilities()
    assert caps["chat"] is True and caps["file_input"] is False
    assert seen == ["image/png", "image/jpeg"]
    supported = [
        mime
        for mime, outcome in [("image/png", png_result), ("image/jpeg", jpeg_result)]
        if outcome == "correct"
    ]
    assert caps["supported_image_mime_types"] == supported
    assert caps["image_input"] is bool(supported)
    if jpeg_result == "rejected":
        assert caps["image_errors"] == {"image/jpeg": "provider_rejected"}
    elif jpeg_result == "timeout":
        assert caps["image_errors"] == {
            "image/png": "probe_content_mismatch",
            "image/jpeg": "provider_timeout",
        }

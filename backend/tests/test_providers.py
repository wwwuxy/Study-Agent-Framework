import json

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core.security import CredentialVault, validate_base_url
from app.providers.base import CapabilityNotSupported, ProviderError
from app.providers.compatible import CompatibleAdapter
from app.schemas.domain import Hint


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/v1",
        "https://169.254.169.254/v1",
        "https://[::1]/v1",
        "https://user:password@example.com/v1",
        "https://example.com/v1?key=secret",
    ],
)
async def test_rejects_private_or_secret_bearing_urls(url):
    with pytest.raises(ProviderError):
        await validate_base_url(url)


def test_encrypted_credentials_round_trip_and_wrong_key_fails():
    vault = CredentialVault(Fernet.generate_key().decode())
    encrypted = vault.encrypt("user-secret")
    assert "user-secret" not in encrypted
    assert vault.decrypt(encrypted) == "user-secret"
    with pytest.raises(ProviderError):
        CredentialVault(Fernet.generate_key().decode()).decrypt(encrypted)


async def public_resolver(host, port):
    return ["93.184.216.34"]


def adapter(handler):
    return CompatibleAdapter(
        "https://example.com/v1",
        "secret",
        "chat",
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
        retries=2,
    )


@pytest.mark.parametrize(
    "status,code", [(401, "invalid_api_key"), (429, "rate_limited"), (500, "provider_unavailable")]
)
async def test_remote_errors_are_classified_without_leaking_secrets(status, code):
    provider = adapter(lambda req: httpx.Response(status, text="secret upstream body"))
    with pytest.raises(ProviderError) as exc:
        await provider.generate_text([{"role": "user", "content": "hi"}])
    assert exc.value.code == code
    assert "secret" not in exc.value.message


async def test_timeout_is_explicit():
    def fail(req):
        raise httpx.ReadTimeout("secret")

    with pytest.raises(ProviderError) as exc:
        await adapter(fail).generate_text([])
    assert exc.value.code == "provider_timeout"


async def test_structured_output_retries_and_usage_is_preserved():
    calls = []

    def respond(req):
        calls.append(req)
        content = "not-json" if len(calls) == 1 else json.dumps({"hint": "从定义出发"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            },
        )

    provider = adapter(respond)
    result = await provider.generate_structured([], Hint.model_json_schema())
    assert result == {"hint": "从定义出发"}
    assert provider.usage["prompt_tokens"] == 20
    # Pin the validated IP while retaining TLS SNI and Host; no DNS rebinding gap.
    assert calls[-1].url.host == "93.184.216.34"
    assert calls[-1].headers["host"] == "example.com"
    assert calls[-1].extensions["sni_hostname"] == "example.com"


async def test_invalid_json_has_bounded_retries():
    attempts = []

    def respond(req):
        attempts.append(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"hint": 3}'}}]})

    with pytest.raises(ProviderError) as exc:
        await adapter(respond).generate_structured([], Hint.model_json_schema())
    assert exc.value.code == "invalid_structured_output"
    assert len(attempts) == 3


async def test_unsupported_features_raise_and_are_not_claimed():
    provider = adapter(
        lambda req: httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})
    )
    caps = await provider.probe_capabilities()
    assert caps["file_input"] is False
    assert caps["embedding"] is False
    with pytest.raises(CapabilityNotSupported):
        await provider.analyze_file("file", {})
    with pytest.raises(CapabilityNotSupported):
        await provider.embed_texts(["text"])

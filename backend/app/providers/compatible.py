import asyncio
import json
from urllib.parse import urlsplit, urlunsplit

import httpx
from jsonschema import ValidationError, validate

from app.core.security import validate_base_url
from app.providers.base import ProviderError, TextOnlyAdapter


class CompatibleAdapter(TextOnlyAdapter):
    def __init__(
        self,
        base_url,
        api_key,
        model,
        timeout=30,
        retries=2,
        allow_private=False,
        transport=None,
        resolver=None,
    ):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model
        self.timeout, self.retries, self.allow_private = timeout, retries, allow_private
        self.transport, self.resolver = transport, resolver
        self.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost": None,
            "cost_status": "unavailable",
            "currency": "USD",
        }

    async def _request(self, messages):
        host, address = await validate_base_url(self.base_url, self.allow_private, self.resolver)
        parsed = urlsplit(self.base_url)
        authority = f"[{address}]" if ":" in address else address
        if parsed.port:
            authority += f":{parsed.port}"
        url = urlunsplit((parsed.scheme, authority, parsed.path + "/chat/completions", "", ""))
        host_header = host + (f":{parsed.port}" if parsed.port else "")
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, transport=self.transport, trust_env=False, follow_redirects=False
                ) as client:
                    response = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {self.api_key}", "Host": host_header},
                        extensions={"sni_hostname": host},
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": 0.2,
                            "max_tokens": 6000,
                        },
                    )
                if response.status_code in (401, 403):
                    raise ProviderError("invalid_api_key", "模型凭证无效或无访问权限", 422)
                if response.status_code == 429:
                    raise ProviderError("rate_limited", "模型提供商限流，请稍后重试", 429)
                if response.status_code >= 500:
                    raise ProviderError("provider_unavailable", "模型服务暂时不可用")
                if response.status_code >= 300:
                    raise ProviderError(
                        "provider_rejected", "模型接口拒绝请求，请检查地址、模型名称和接口兼容性"
                    )
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("missing text")
                for key in ("prompt_tokens", "completion_tokens"):
                    value = data.get("usage", {}).get(key)
                    if isinstance(value, int) and value >= 0:
                        self.usage[key] += value
                return text
            except httpx.TimeoutException:
                error = ProviderError("provider_timeout", "模型请求超时，可以重新发起")
            except httpx.RequestError:
                error = ProviderError("provider_unavailable", "无法连接模型服务")
            except (ValueError, KeyError, IndexError, TypeError):
                raise ProviderError("invalid_provider_response", "模型接口返回了无效响应") from None
            except ProviderError as exc:
                if exc.code not in {"rate_limited", "provider_unavailable"}:
                    raise
                error = exc
            if attempt == self.retries:
                raise error
            await asyncio.sleep(0.1 * (2**attempt))

    async def generate_text(self, messages):
        return await self._request(messages)

    async def generate_structured(self, messages, schema):
        instruction = {
            "role": "system",
            "content": "只输出符合以下 JSON Schema 的 JSON 对象，不要 Markdown："
            + json.dumps(schema, ensure_ascii=False),
        }
        for _ in range(self.retries + 1):
            text = await self._request([instruction, *messages])
            try:
                data = json.loads(text)
                validate(data, schema)
                return data
            except (ValueError, ValidationError):
                continue
        raise ProviderError("invalid_structured_output", "模型连续返回非法结构化内容；任务已停止，可重试")

    async def probe_capabilities(self):
        await self.generate_text([{"role": "user", "content": "请回复 OK，用于用户授权的连通性检测。"}])
        await self.generate_structured(
            [{"role": "user", "content": '请返回 {"ok":true}'}],
            {
                "type": "object",
                "properties": {"ok": {"const": True}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        )
        return {
            "chat": True,
            "structured_json": True,
            "structured_mode": "prompt_validated",
            "file_input": False,
            "supported_mime_types": [],
            "embedding": False,
            "web_search": False,
            "tool_calling": False,
            "adapter": "openai_compatible",
        }

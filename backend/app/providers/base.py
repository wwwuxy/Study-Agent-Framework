from typing import Protocol


class ProviderError(Exception):
    def __init__(self, code: str, message: str, status: int = 502):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class CapabilityNotSupported(ProviderError):
    def __init__(self):
        super().__init__("capability_not_supported", "当前适配器未验证或不支持这项模型能力", 422)


class ProviderAdapter(Protocol):
    usage: dict

    async def probe_capabilities(self) -> dict: ...
    async def generate_text(self, messages: list[dict]) -> str: ...
    async def generate_structured(self, messages: list[dict], schema: dict) -> dict: ...
    async def analyze_file(self, file_ref: str, task: dict) -> dict: ...
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class TextOnlyAdapter:
    async def analyze_file(self, file_ref, task):
        raise CapabilityNotSupported()

    async def embed_texts(self, texts):
        raise CapabilityNotSupported()

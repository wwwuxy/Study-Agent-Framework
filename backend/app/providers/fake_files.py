import json

from app.providers.base import CapabilityNotSupported
from app.providers.fake import FakeAdapter


class FakeFileAdapter(FakeAdapter):
    """Explicit fixtures only: never parses user content, never a real capability claim."""

    def __init__(self, embedding_model=None):
        super().__init__()
        self.embedding_model = embedding_model

    async def probe_capabilities(self):
        return {
            **await super().probe_capabilities(),
            "adapter": "fake_files",
            "file_input": True,
            "supported_mime_types": ["application/pdf"],
            "embedding": bool(self.embedding_model),
            "locator_verified": False,
            "is_demo": True,
        }

    async def upload_file(self, content, filename):
        return "demo-file"

    async def delete_file(self, ref):
        return None

    async def analyze_file(self, file_ref, task):
        if task["schema"]["title"] == "RemoteOutline":
            return {
                "title": "离线演示教材（未读取上传内容）",
                "sections": [{"section_id": "os", "heading": "操作系统基础"}],
            }
        section = task["section"]
        return {
            "section_id": section["section_id"],
            "heading": section["heading"],
            "summary": "离线演示：操作系统管理 CPU、内存和设备。未读取上传文件内容。",
            "keywords": ["操作系统", "内存管理"],
            "concepts": ["操作系统的职责"],
            "locator": {"chapter": section["heading"], "page": None},
            "locator_verified": False,
        }

    async def embed_texts(self, texts):
        if not self.embedding_model:
            raise CapabilityNotSupported()
        return [[1.0, float("内存" in text) + 0.1, 0.5] for text in texts]

    async def generate_structured(self, messages, schema):
        task = json.loads(messages[-1]["content"])
        ids = [s["source_id"] for s in task.get("sources", [])]
        if schema.get("title") == "Rerank":
            return {"source_ids": ids[: task.get("limit", 5)]}
        result = await super().generate_structured(messages, schema)
        if ids:
            if schema.get("title") == "LessonContent":
                result["source_ids"] = ids
                for q in result["exercises"]:
                    q["source_ids"] = ids
            if schema.get("title") == "QuestionBatch":
                for q in result["items"]:
                    q["source_ids"] = ids
        return result

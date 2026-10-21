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
            "image_input": True,
            "supported_image_mime_types": ["image/png", "image/jpeg"],
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

    async def analyze_exam(self, inputs, task, *, max_output_tokens):
        keys = task.get("concept_ids", [])
        name = task.get("concepts", [{}])[0].get("name", "操作系统知识")
        return {
            "title": "离线演示试卷（未读取上传内容）",
            "coverage_complete": True,
            "coverage_note": "固定样例，不代表真实识别能力",
            "questions": [
                {
                    "key": "q1",
                    "number": "1",
                    "source_id": inputs[0].attachment_id,
                    "prompt": f"请解释{name}的含义",
                    "student_answer": "演示：给出完整定义与实例",
                    "teacher_marks": "✓",
                    "teacher_mark_clear": True,
                    "teacher_result": "correct",
                    "result": "correct",
                    "recognition_confidence": "high",
                    "mapping_confidence": "high",
                    "concept_ids": keys[:1],
                },
                {
                    "key": "q2",
                    "number": "2",
                    "source_id": inputs[0].attachment_id,
                    "prompt": f"举例说明{name}的应用",
                    "student_answer": "演示：回答不完整",
                    "teacher_marks": "×",
                    "teacher_mark_clear": True,
                    "teacher_result": "incorrect",
                    "result": "incorrect",
                    "recognition_confidence": "high",
                    "mapping_confidence": "high",
                    "concept_ids": keys[:1],
                },
            ],
        }

    async def embed_texts(self, texts):
        if not self.embedding_model:
            raise CapabilityNotSupported()
        return [[1.0, float("内存" in text) + 0.1, 0.5] for text in texts]

    async def generate_structured(self, messages, schema):
        task = json.loads(messages[-1]["content"])
        if schema.get("title") == "ExamAdvice":
            return {
                "summary": "离线演示：本卷有答对与答错的知识，需要结合原题巩固。未读取上传内容。",
                "suggestions": [],
            }
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

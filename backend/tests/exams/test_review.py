import asyncio

from app.exam_diagnostics.worker import tick
from app.providers.fake_files import FakeFileAdapter

from .test_uploads import create, put


class MappingAdapter(FakeFileAdapter):
    async def analyze_exam(self, inputs, task, **kw):
        raw = await super().analyze_exam(inputs, task, **kw)
        raw["questions"][0]["mapping_confidence"] = "low"
        raw["questions"][1]["teacher_mark_clear"] = False
        return raw


def test_mapping_only_review_adds_clear_teacher_evidence_once(exam_env, pdf_bytes):
    exam_env.app.state.adapter_factory = lambda cfg: MappingAdapter()
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "s"}
    )
    asyncio.run(tick(exam_env.app))
    result = exam_env.client.get(exam_env.root + "/" + row["id"]).json()
    assert result["effective_evidence_count"] == 0
    q = result["questions"][0]
    body = {"expected_version": 1, "concept_ids": [exam_env.concepts[0]], "idempotency_key": "fix"}
    url = exam_env.root + "/" + row["id"] + "/questions/" + q["id"]
    patched = exam_env.client.patch(url, json=body)
    assert patched.status_code == 200, patched.text
    assert patched.json()["effective_evidence_count"] == 1
    assert exam_env.client.patch(url, json=body).json()["effective_evidence_count"] == 1
    unclear = result["questions"][1]
    response = exam_env.client.patch(
        exam_env.root + "/" + row["id"] + "/questions/" + unclear["id"],
        json={
            "expected_version": 1,
            "result": "correct",
            "concept_ids": [exam_env.concepts[0]],
            "idempotency_key": "manual",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["effective_evidence_count"] == 1

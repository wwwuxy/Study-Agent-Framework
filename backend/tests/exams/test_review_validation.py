import asyncio

from app.exam_diagnostics.worker import tick

from .test_review import MappingAdapter
from .test_uploads import create, put


def test_invalid_review_score_is_422_not_server_error(exam_env, pdf_bytes):
    exam_env.app.state.adapter_factory = lambda c: MappingAdapter()
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "s"}
    )
    asyncio.run(tick(exam_env.app))
    detail = exam_env.client.get(exam_env.root + "/" + row["id"]).json()
    q = detail["questions"][0]
    response = exam_env.client.patch(
        exam_env.root + "/" + row["id"] + "/questions/" + q["id"],
        json={"expected_version": 1, "score": 10, "max_score": 5, "idempotency_key": "badscore"},
    )
    assert response.status_code == 422

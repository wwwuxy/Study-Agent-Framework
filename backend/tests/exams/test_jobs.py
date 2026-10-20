import asyncio

from sqlalchemy import select

from app.db.models import LearningEvent
from app.exam_diagnostics.worker import tick

from .test_uploads import create, put


def test_pdf_completion_and_duplicate_do_not_multiply_evidence(exam_env, pdf_bytes):
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    response = exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "start1"}
    )
    assert response.status_code == 202, response.text
    asyncio.run(tick(exam_env.app))
    result = exam_env.client.get(exam_env.root + "/" + row["id"]).json()
    assert result["status"] == "completed", result
    assert result["effective_evidence_count"] == 2
    again = create(exam_env, pdf_bytes, key="duplicate")
    put(exam_env, again, pdf_bytes)
    duplicate = exam_env.client.post(
        exam_env.root + "/" + again["id"] + "/start", json={"consent": True, "idempotency_key": "start2"}
    ).json()
    assert duplicate["id"] == row["id"]
    with exam_env.app.state.session_factory() as db:
        assert (
            len(db.scalars(select(LearningEvent).where(LearningEvent.type == "exam_question_imported")).all())
            == 2
        )


def test_start_requires_complete_upload_and_consent(exam_env, pdf_bytes):
    row = create(exam_env, pdf_bytes)
    url = exam_env.root + "/" + row["id"] + "/start"
    assert exam_env.client.post(url, json={"consent": True, "idempotency_key": "s"}).status_code == 409
    put(exam_env, row, pdf_bytes)
    assert exam_env.client.post(url, json={"consent": False, "idempotency_key": "s"}).status_code == 422


def test_remote_handle_is_registered_when_maintenance_begins_during_upload(exam_env, pdf_bytes):
    from pathlib import Path

    from app.exam_diagnostics.models import ExamJob
    from app.providers.base import ProviderError
    from app.providers.fake_files import FakeFileAdapter

    marker = Path(exam_env.app.state.settings.material_storage_dir) / ".maintenance-lock"

    class DuringMaintenance(FakeFileAdapter):
        async def upload_file(self, *args):
            marker.write_text("test-only-maintenance")
            return "late-remote-file"

    exam_env.app.state.adapter_factory = lambda config: DuringMaintenance()
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "start"}
    )

    async def process():
        try:
            await tick(exam_env.app)
        except ProviderError as error:
            assert error.code == "maintenance"

    try:
        asyncio.run(process())
        with exam_env.app.state.session_factory() as db:
            jobs = db.scalars(
                select(ExamJob).where(ExamJob.diagnostic_id == row["id"], ExamJob.kind == "recognize")
            ).all()
            assert [ref["ref"] for job in jobs for ref in job.data.get("remote_files", [])] == [
                "late-remote-file"
            ]
            assert (
                db.scalar(select(LearningEvent.id).where(LearningEvent.type == "exam_question_imported"))
                is None
            )
    finally:
        marker.unlink(missing_ok=True)

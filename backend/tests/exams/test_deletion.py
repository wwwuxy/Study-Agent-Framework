import asyncio
from pathlib import Path

from sqlalchemy import select

from app.exam_diagnostics.models import ExamQuestion
from app.exam_diagnostics.worker import tick

from .test_uploads import create, put


def test_space_deletion_erases_exam_files_and_questions(exam_env, pdf_bytes):
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "s"}
    )
    asyncio.run(tick(exam_env.app))
    response = exam_env.client.delete("/api/v1/study-spaces/" + exam_env.space_id)
    assert response.status_code == 200, response.text
    with exam_env.app.state.session_factory() as db:
        assert db.scalar(select(ExamQuestion.id).where(ExamQuestion.space_id == exam_env.space_id)) is None
    assert not list((Path(exam_env.app.state.settings.material_storage_dir) / "exams").rglob("*.bin"))
    assert exam_env.client.get(exam_env.root + "/" + row["id"]).status_code == 404


def test_reset_with_failed_exam_cleanup_is_resumable(exam_env, pdf_bytes, monkeypatch):
    from app.maintenance.reset_learning import reset_learning
    from app.providers.base import ProviderError
    from app.providers.fake_files import FakeFileAdapter

    async def broken(self, ref):
        raise ProviderError("remote_delete_failed", "delete unavailable")

    monkeypatch.setattr(FakeFileAdapter, "delete_file", broken)
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "s"}
    )
    asyncio.run(tick(exam_env.app))
    settings = exam_env.app.state.settings
    preview = asyncio.run(reset_learning(settings, "reset-exams"))
    result = asyncio.run(
        reset_learning(settings, "reset-exams", apply=True, expected_target=preview["fingerprint"])
    )
    assert result["status"] == "cleanup_pending"
    assert result["remote_pending"] == 1

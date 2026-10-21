import asyncio
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.orchestrator import event_data
from app.db.models import LearningEvent, ReviewState, StudySpace, utcnow
from app.exam_diagnostics import cleanup, queue
from app.exam_diagnostics.models import ExamAttachment, ExamDiagnostic, ExamJob
from app.exam_diagnostics.publication import publish
from app.exam_diagnostics.worker import tick
from app.providers.base import ProviderError
from app.schemas.exams import ExamAdvice

from .test_publication import prepared
from .test_uploads import create, put


def test_delete_completed_diagnostic_retracts_only_its_evidence_and_preserves_memory(
    exam_env, recognition_payload, pdf_bytes
):
    claim, rec = prepared(exam_env, recognition_payload, pdf_bytes)
    with exam_env.app.state.session_factory.begin() as db:
        asyncio.run(
            publish(
                db,
                db.get(StudySpace, exam_env.space_id),
                claim,
                rec,
                ExamAdvice(summary="test"),
                now=utcnow(),
            )
        )
        memory = [(s.id, s.card, s.due) for s in db.scalars(select(ReviewState))]
    second = create(exam_env, pdf_bytes + b"\n%second", key="second")
    put(exam_env, second, pdf_bytes + b"\n%second")
    exam_env.client.post(
        exam_env.root + "/" + second["id"] + "/start",
        json={"consent": True, "idempotency_key": "second-start"},
    )
    asyncio.run(tick(exam_env.app))
    target = exam_env.root + "/" + claim.diagnostic_id
    response = exam_env.client.delete(target)
    assert response.status_code == 204, response.text
    assert exam_env.client.delete(target).status_code == 204
    assert exam_env.client.get(target).status_code == 404
    assert [r["id"] for r in exam_env.client.get(exam_env.root).json()["items"]] == [second["id"]]
    report = exam_env.client.get(f"/api/v1/study-spaces/{exam_env.space_id}/report").json()
    assert report["external_imports"] == {
        "diagnostics": 1,
        "effective_evidence": 2,
        "window_basis": "imported_at",
    }
    with exam_env.app.state.session_factory() as db:
        assert (
            len(list(db.scalars(select(LearningEvent).where(LearningEvent.type == "exam_question_imported"))))
            == 4
        )
        assert (
            len(
                list(db.scalars(select(LearningEvent).where(LearningEvent.type == "exam_diagnostic_deleted")))
            )
            == 1
        )
        assert {
            e["diagnostic_id"]
            for e in event_data(db, exam_env.space_id)
            if e["type"] == "exam_question_imported"
        } == {second["id"]}
        assert [(s.id, s.card, s.due) for s in db.scalars(select(ReviewState))] == memory
    detail = exam_env.client.get(exam_env.root + "/" + second["id"]).json()
    current = exam_env.client.get(f"/api/v1/study-spaces/{exam_env.space_id}/profile").json()
    assert sum(s["evidence_count"] for s in current["states"]) == 2
    assert detail["status"] == "completed"


@pytest.mark.parametrize("running", [False, True])
def test_delete_pending_diagnostic_fences_worker_erases_files_and_allows_reupload(
    exam_env, pdf_bytes, running
):
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "start"}
    )
    claim = queue.claim(exam_env.app.state.session_factory, utcnow()) if running else None
    assert exam_env.client.delete(exam_env.root + "/" + row["id"]).status_code == 204
    assert not list((Path(exam_env.app.state.settings.material_storage_dir) / "exams").rglob("*.bin"))
    if claim:
        with pytest.raises(ProviderError, match="过期|取消"):
            queue.checkpoint(exam_env.app.state.session_factory, claim, "analyzing", None)
        cleanup.register_remote(
            exam_env.app.state.session_factory,
            claim,
            exam_env.provider_id,
            "late-file",
            provider_snapshot={"id": exam_env.provider_id},
        )
    with exam_env.app.state.session_factory() as db:
        assert db.get(ExamDiagnostic, row["id"]).status == "deleted"
        assert not list(db.scalars(select(ExamAttachment).where(ExamAttachment.diagnostic_id == row["id"])))
        source = db.scalar(
            select(ExamJob).where(ExamJob.diagnostic_id == row["id"], ExamJob.kind == "recognize")
        )
        assert source.status == "cancelled" and source.active_space_id is None
        if running:
            assert db.scalar(
                select(ExamJob.id).where(ExamJob.diagnostic_id == row["id"], ExamJob.kind == "cleanup")
            )
    again = create(exam_env, pdf_bytes, key="new-upload")
    put(exam_env, again, pdf_bytes)
    response = exam_env.client.post(
        exam_env.root + "/" + again["id"] + "/start", json={"consent": True, "idempotency_key": "new-start"}
    )
    assert response.status_code == 202 and response.json()["id"] == again["id"]


def test_deletion_rolls_back_when_state_rebuild_fails(exam_env, recognition_payload, pdf_bytes, monkeypatch):
    import app.exam_diagnostics.deletion as deletion

    claim, rec = prepared(exam_env, recognition_payload, pdf_bytes)
    with exam_env.app.state.session_factory.begin() as db:
        asyncio.run(
            publish(
                db,
                db.get(StudySpace, exam_env.space_id),
                claim,
                rec,
                ExamAdvice(summary="test"),
                now=utcnow(),
            )
        )

    async def broken(*args):
        raise ArithmeticError("state rebuild failed")

    monkeypatch.setattr(deletion, "rebuild_states", broken)
    with pytest.raises(ArithmeticError):
        exam_env.client.delete(exam_env.root + "/" + claim.diagnostic_id)
    assert exam_env.client.get(exam_env.root + "/" + claim.diagnostic_id).json()["status"] == "completed"
    assert list((Path(exam_env.app.state.settings.material_storage_dir) / "exams").rglob("*.bin"))


def test_foreign_user_cannot_delete_diagnostic(exam_env, pdf_bytes):
    row = create(exam_env, pdf_bytes)
    exam_env.client.post("/api/v1/auth/logout")
    exam_env.client.post(
        "/api/v1/auth/register", json={"username": "other", "password": "strong-password-2026"}
    )
    assert exam_env.client.delete(exam_env.root + "/" + row["id"]).status_code == 404

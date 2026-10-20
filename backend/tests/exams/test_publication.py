import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import LearningEvent, ProviderConfig, StudySpace, utcnow
from app.exam_diagnostics.contracts import ExamClaim
from app.exam_diagnostics.models import ExamDiagnostic, ExamJob
from app.exam_diagnostics.publication import publish
from app.exam_diagnostics.recognition import normalize
from app.knowledge.materials import fingerprint
from app.schemas.exams import ExamAdvice, ExamRecognition

from .test_uploads import create, put


def prepared(env, payload, pdf_bytes):
    row = create(env, pdf_bytes)
    put(env, row, pdf_bytes)
    claim = ExamClaim("job1", row["id"], row["study_space_id"], "unused", "token", 1)
    with env.app.state.session_factory.begin() as db:
        space = db.get(StudySpace, env.space_id)
        diag = db.get(ExamDiagnostic, row["id"])
        diag.status = "running"
        claim = ExamClaim("job1", diag.id, space.user_id, space.id, "token", 1)
        config = db.get(ProviderConfig, space.provider_id)
        db.add(
            ExamJob(
                id="job1",
                user_id=space.user_id,
                space_id=space.id,
                diagnostic_id=diag.id,
                request_key="start",
                status="running",
                active_space_id=space.id,
                lease_token="token",
                lease_until=utcnow() + timedelta(seconds=180),
                provider_id=config.id,
                data={"provider_fingerprint": fingerprint(config)},
            )
        )
    rec = normalize(ExamRecognition.model_validate(payload), {"a1"}, set(env.concepts))
    return claim, rec


def test_report_and_real_states_publish_atomically(exam_env, recognition_payload, pdf_bytes):
    claim, rec = prepared(exam_env, recognition_payload, pdf_bytes)
    with exam_env.app.state.session_factory.begin() as db:
        result = asyncio.run(
            publish(
                db,
                db.get(StudySpace, exam_env.space_id),
                claim,
                rec,
                ExamAdvice(summary="需巩固"),
                now=utcnow(),
            )
        )
        assert result.status == "completed" and result.effective_evidence_count == 2
        assert result.after[exam_env.concepts[0]]["evidence_count"] == 2
        assert result.after[exam_env.concepts[0]]["independent_correct_count"] == 0
    progress = exam_env.client.get(f"/api/v1/study-spaces/{exam_env.space_id}/report").json()
    assert progress["evidence"]["answers"] == 0
    assert progress["external_imports"]["effective_evidence"] == 2


def test_estimator_failure_rolls_back_everything(exam_env, recognition_payload, pdf_bytes, monkeypatch):
    import app.exam_diagnostics.publication as publication

    claim, rec = prepared(exam_env, recognition_payload, pdf_bytes)

    async def broken(*args):
        raise ArithmeticError("failed")

    monkeypatch.setattr(publication, "rebuild_states", broken)
    with pytest.raises(ArithmeticError):
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
    with exam_env.app.state.session_factory() as db:
        assert db.get(ExamDiagnostic, claim.diagnostic_id).status == "running"
        assert (
            db.scalar(select(LearningEvent.id).where(LearningEvent.type == "exam_question_imported")) is None
        )

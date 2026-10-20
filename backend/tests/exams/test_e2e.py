import asyncio
import hashlib
import io

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.db.models import LearningEvent, ReviewState
from app.exam_diagnostics.worker import tick
from app.main import create_app
from app.providers.fake_files import FakeFileAdapter

from .test_uploads import create, put


def test_images_update_shared_state_after_restart_and_reorder(exam_env, image_bytes):
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "black").save(stream, format="PNG")
    files = [image_bytes, stream.getvalue()]

    def upload(key, content):
        row = exam_env.client.post(
            exam_env.root,
            json={
                "name": "图片试卷",
                "idempotency_key": key,
                "attachments": [
                    {
                        "client_id": f"a{i + 1}",
                        "filename": f"{i}.png",
                        "mime_type": "image/png",
                        "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                    for i, data in enumerate(content)
                ],
            },
        ).json()
        for a, data in zip(row["attachments"], content, strict=True):
            assert (
                exam_env.client.put(
                    exam_env.root + "/" + row["id"] + "/attachments/" + a["id"],
                    content=data,
                    headers={"content-type": "image/png"},
                ).status_code
                == 200
            )
        return exam_env.client.post(
            exam_env.root + "/" + row["id"] + "/start",
            json={"consent": True, "idempotency_key": key + "start"},
        ).json()

    with exam_env.app.state.session_factory() as db:
        before = [
            (s.concept_id, s.card, s.due)
            for s in db.scalars(select(ReviewState).where(ReviewState.space_id == exam_env.space_id))
        ]
    row = upload("images", files)
    asyncio.run(tick(exam_env.app))
    original = exam_env.client.get(exam_env.root + "/" + row["id"]).json()
    assert original["status"] == "completed" and original["effective_evidence_count"] == 2
    assert upload("reverse", files[::-1])["id"] == row["id"]
    app = create_app(exam_env.app.state.settings)
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "alice", "password": "strong-password-2026"}
            ).status_code
            == 200
        )
        restored = client.get(exam_env.root + "/" + row["id"]).json()
        assert restored["after"] == original["after"]
        assert restored["effective_evidence_count"] == 2
    with exam_env.app.state.session_factory() as db:
        after = [
            (s.concept_id, s.card, s.due)
            for s in db.scalars(select(ReviewState).where(ReviewState.space_id == exam_env.space_id))
        ]
        assert before == after
        assert (
            len(db.scalars(select(LearningEvent).where(LearningEvent.type == "exam_question_imported")).all())
            == 2
        )


def test_failed_publish_retry_keeps_checkpoints_and_state_consistent(exam_env, pdf_bytes, monkeypatch):
    import app.exam_diagnostics.publication as publication

    calls = []

    class RecordingAdapter(FakeFileAdapter):
        async def upload_file(self, *args):
            calls.append("upload")
            return await super().upload_file(*args)

        async def analyze_exam(self, *args, **kw):
            calls.append("recognize")
            return await super().analyze_exam(*args, **kw)

        async def generate_structured(self, *args, **kw):
            calls.append("advice")
            return await super().generate_structured(*args, **kw)

    exam_env.app.state.adapter_factory = lambda cfg: RecordingAdapter()
    original_rebuild = publication.rebuild_states

    async def fail(*args):
        raise ArithmeticError("failure")

    monkeypatch.setattr(publication, "rebuild_states", fail)
    row = create(exam_env, pdf_bytes)
    put(exam_env, row, pdf_bytes)
    exam_env.client.post(
        exam_env.root + "/" + row["id"] + "/start", json={"consent": True, "idempotency_key": "s"}
    )
    asyncio.run(tick(exam_env.app))
    failed = exam_env.client.get(exam_env.root + "/" + row["id"]).json()
    assert failed["status"] == "failed" and failed["effective_evidence_count"] == 0
    monkeypatch.setattr(publication, "rebuild_states", original_rebuild)
    assert (
        exam_env.client.post(
            exam_env.root + "/" + row["id"] + "/retry", json={"consent": False, "idempotency_key": "retry"}
        ).status_code
        == 202
    )
    asyncio.run(tick(exam_env.app))
    result = exam_env.client.get(exam_env.root + "/" + row["id"]).json()
    assert result["status"] == "completed" and result["effective_evidence_count"] == 2
    assert calls == ["upload", "recognize", "advice"]

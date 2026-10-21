from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import provider, register, space
from sqlalchemy import delete, select
from test_materials import configure, process, upload

from app.db.models import (
    AgentRun,
    AssessmentAttempt,
    AssessmentItem,
    ConceptPrerequisite,
    KnowledgeConcept,
    LearnerConceptState,
    LearningEvent,
    LearningPlan,
    Lesson,
    MaterialAsset,
    MaterialJob,
    MaterialSection,
    StudySpace,
)
from app.providers.base import ProviderError
from app.providers.fake_files import FakeFileAdapter


def test_delete_space_permanently_erases_learning_content_and_cannot_restore(client, settings):
    register(client)
    pid = provider(client)
    sid = space(client, pid)
    other = space(client, pid, key="second")
    root = f"/api/v1/study-spaces/{sid}"
    lesson = client.post(root + "/lessons", json={"idempotency_key": "lesson"}).json()
    assert (
        client.post(
            root + "/attempts",
            json={
                "item_id": lesson["exercises"][0]["id"],
                "answer": "A",
                "idempotency_key": "attempt",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(root + f"/lessons/{lesson['id']}/complete", json={"idempotency_key": "read"}).status_code
        == 200
    )
    assert client.get(root + "/events").json()
    with client.app.state.session_factory() as db:
        assert db.scalars(select(AssessmentAttempt).where(AssessmentAttempt.space_id == sid)).all()
        uid = db.get(StudySpace, sid).user_id
    # A crashed local upload may leave a staging file without an asset row.
    private_dir = Path(settings.material_storage_dir) / uid / sid
    other_dir = Path(settings.material_storage_dir) / uid / other
    private_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    (private_dir / ".upload-orphan.part").write_bytes(b"private textbook bytes")
    other_file = other_dir / "retained.bin"
    other_file.write_bytes(b"other space textbook")
    with client.app.state.session_factory() as db, pytest.raises(Exception, match="append.only"):
        db.execute(delete(LearningEvent).where(LearningEvent.space_id == sid))
    removed = client.delete(root)
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "deleted"
    assert not private_dir.exists()
    assert other_file.read_bytes() == b"other space textbook"
    assert [row["id"] for row in client.get("/api/v1/study-spaces").json()] == [other]
    assert [row["id"] for row in client.get("/api/v1/study-spaces?include_archived=true").json()] == [other]
    for suffix in ["", "/events", "/concepts", "/profile", "/plan", "/lessons/current", "/materials"]:
        assert client.get(root + suffix).status_code == 404
    assert client.post(root + "/restore").status_code == 404
    assert client.delete(root).status_code == 200
    with client.app.state.session_factory() as db:
        for model in (
            LearningEvent,
            AssessmentAttempt,
            AssessmentItem,
            Lesson,
            LearnerConceptState,
            ConceptPrerequisite,
            KnowledgeConcept,
            LearningPlan,
            AgentRun,
        ):
            assert not db.scalars(select(model).where(model.space_id == sid)).all(), model
        tombstone = db.get(StudySpace, sid)
        assert tombstone.goal == "" and tombstone.provider_id is None
    assert client.get(f"/api/v1/study-spaces/{other}/concepts").json()
    assert client.get("/api/v1/providers").json()[0]["id"] == pid


def test_delete_space_removes_local_textbooks_and_exposes_retryable_remote_cleanup(client, settings):
    pid, sid = configure(client)
    asset = upload(client, sid).json()
    process(client, asset["job_id"])
    assert list(Path(settings.material_storage_dir).rglob("*.bin"))
    assert client.delete(f"/api/v1/study-spaces/{sid}").status_code == 200
    assert not list(Path(settings.material_storage_dir).rglob("*.bin"))
    with client.app.state.session_factory() as db:
        assert not db.scalars(select(MaterialSection).where(MaterialSection.space_id == sid)).all()
        stored = db.get(MaterialAsset, asset["id"])
        assert stored.filename == "" and stored.sha256 == "" and stored.size_bytes == 0
        assert all(not row.data for row in db.scalars(select(MaterialJob).where(MaterialJob.kind == "index")))

    class FailingDelete(FakeFileAdapter):
        async def delete_file(self, ref):
            raise ProviderError("provider_unavailable", "远端删除暂时失败，请重试")

    client.app.state.adapter_factory = lambda _: FailingDelete()
    cleanup = client.get("/api/v1/study-spaces/deletion-jobs").json()
    assert len(cleanup) == 1 and cleanup[0]["space_id"] == sid
    failed = client.post(f"/api/v1/jobs/{cleanup[0]['id']}/run").json()
    assert failed["status"] == "failed"
    assert client.get("/api/v1/study-spaces/deletion-jobs").json()[0]["status"] == "failed"
    assert client.delete(f"/api/v1/providers/{pid}").status_code == 409
    retry = client.post(
        f"/api/v1/jobs/{cleanup[0]['id']}/retry", json={"idempotency_key": "clean-retry"}
    ).json()
    client.app.state.adapter_factory = lambda _: FakeFileAdapter()
    process(client, retry["id"])
    assert client.get("/api/v1/study-spaces/deletion-jobs").json() == []
    assert client.delete(f"/api/v1/providers/{pid}").status_code == 204
    with client.app.state.session_factory() as db:
        assert not db.scalars(select(AgentRun).where(AgentRun.space_id == sid)).all()


def test_checkpoint_cannot_reintroduce_text_after_permanent_deletion(client, monkeypatch):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    from app.api.spaces import remove_space
    from app.jobs import materials

    _, sid = configure(client)
    asset = upload(client, sid).json()
    original = materials.checkpoint

    async def erase():
        with client.app.state.session_factory() as db:
            uid = db.get(StudySpace, sid).user_id
            await remove_space(sid, SimpleNamespace(app=client.app), db, SimpleNamespace(id=uid))
            db.commit()

    def delete_before_checkpoint(db, job, stage, progress, **values):
        if stage == "sections":
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(asyncio.run, erase()).result(timeout=10)
        return original(db, job, stage, progress, **values)

    monkeypatch.setattr(materials, "checkpoint", delete_before_checkpoint)
    client.portal.call(materials.run_job, client.app, asset["job_id"])
    with client.app.state.session_factory() as db:
        assert db.get(StudySpace, sid).status == "deleted"
        job = db.get(MaterialJob, asset["job_id"])
        assert job.status == "cancelled" and job.data == {}
        assert not db.scalars(select(MaterialSection).where(MaterialSection.space_id == sid)).all()


def test_failed_model_call_cannot_recreate_audit_after_deletion(client):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import event

    from app.api.spaces import remove_space
    from app.core.orchestrator import call_model
    from app.db.models import ProviderConfig

    pid, sid = configure(client)

    class Failing(FakeFileAdapter):
        async def probe_capabilities(self):
            raise ProviderError("provider_unavailable", "failure")

    client.app.state.adapter_factory = lambda _: Failing()

    async def scenario():
        with client.app.state.session_factory() as db:
            config = db.get(ProviderConfig, pid)
            uid = config.user_id
            entered = False

            def erase_after_rollback(session):
                nonlocal entered
                if entered:
                    return
                entered = True

                async def erase():
                    with client.app.state.session_factory() as other:
                        await remove_space(
                            sid, SimpleNamespace(app=client.app), other, SimpleNamespace(id=uid)
                        )
                        other.commit()

                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(asyncio.run, erase()).result(timeout=10)

            event.listen(db, "after_rollback", erase_after_rollback)
            with pytest.raises(ProviderError):
                await call_model(SimpleNamespace(app=client.app), db, config, sid, "lesson")
        with client.app.state.session_factory() as db:
            assert db.get(StudySpace, sid).status == "deleted"
            assert not db.scalars(select(AgentRun).where(AgentRun.space_id == sid)).all()

    client.portal.call(scenario)


def test_delete_cancels_pending_indexing_and_prevents_creation_replay(client):
    pid, sid = configure(client)
    asset = upload(client, sid).json()
    root = f"/api/v1/study-spaces/{sid}"
    assert client.delete(root).status_code == 200
    with client.app.state.session_factory() as db:
        assert db.get(MaterialJob, asset["job_id"]).status == "cancelled"
    assert client.post(f"/api/v1/jobs/{asset['job_id']}/run").status_code == 404
    response = client.post(
        "/api/v1/study-spaces",
        json={"provider_id": pid, "goal": "学习操作系统", "idempotency_key": "space-1", "daily_minutes": 30},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "space_deleted"


def test_deletion_and_cleanup_remain_user_isolated(client):
    _, sid = configure(client)
    asset = upload(client, sid).json()
    process(client, asset["job_id"])
    client.delete(f"/api/v1/study-spaces/{sid}")
    cleanup = client.get("/api/v1/study-spaces/deletion-jobs").json()[0]
    client.post("/api/v1/auth/logout")
    register(client, "otheruser")
    assert client.delete(f"/api/v1/study-spaces/{sid}").status_code == 404
    assert client.get("/api/v1/study-spaces/deletion-jobs").json() == []
    assert client.post(f"/api/v1/jobs/{cleanup['id']}/run").status_code == 404


def test_upload_finishing_after_space_deletion_is_still_cleaned(client):
    from app.api.providers import remove_provider
    from app.api.spaces import remove_space
    from app.jobs.materials import run_job

    pid, sid = configure(client)
    deleted_refs = []

    class LateUpload(FakeFileAdapter):
        async def upload_file(self, content, filename):
            with client.app.state.session_factory() as db:
                original = db.get(StudySpace, sid)
                await remove_space(
                    sid, SimpleNamespace(app=client.app), db, SimpleNamespace(id=original.user_id)
                )
                db.commit()
                first_cleanup = db.scalar(select(MaterialJob.id).where(MaterialJob.kind == "cleanup"))
                user = SimpleNamespace(id=original.user_id)
            await run_job(client.app, first_cleanup)
            with client.app.state.session_factory() as db:
                assert db.get(MaterialAsset, asset["id"]).status == "deleting"
                with pytest.raises(ProviderError) as error:
                    await remove_provider(pid, db, user)
                assert error.value.code == "provider_in_use"
            return "late-remote-file"

        async def delete_file(self, ref):
            deleted_refs.append(ref)

    client.app.state.adapter_factory = lambda _: LateUpload()
    asset = upload(client, sid).json()
    client.portal.call(run_job, client.app, asset["job_id"])
    jobs = client.get("/api/v1/study-spaces/deletion-jobs").json()
    assert jobs
    for job in jobs:
        if job["kind"] == "cleanup" and job["status"] == "queued":
            process(client, job["id"])
    assert "late-remote-file" in deleted_refs
    assert client.get("/api/v1/study-spaces/deletion-jobs").json() == []
    with client.app.state.session_factory() as db:
        assert not db.get(MaterialAsset, asset["id"]).remote_files
        assert not db.scalars(select(AgentRun).where(AgentRun.space_id == sid)).all()


def test_cleanup_durably_resumes_when_cancelled_uploader_crashes(client):
    from datetime import timedelta

    from app.db.models import utcnow

    pid, sid = configure(client)
    asset = upload(client, sid).json()
    with client.app.state.session_factory() as db:
        job = db.get(MaterialJob, asset["job_id"])
        job.status, job.lease_until = "running", utcnow() + timedelta(seconds=120)
        job.data = {"_lease": "crashed-process", "_upload_provider_id": pid}
        db.commit()
    assert client.delete(f"/api/v1/study-spaces/{sid}").status_code == 200
    cleanup = next(
        job for job in client.get("/api/v1/study-spaces/deletion-jobs").json() if job["kind"] == "cleanup"
    )
    response = client.post(f"/api/v1/jobs/{cleanup['id']}/run").json()
    assert response["status"] == "running" and response["stage"] == "waiting_upload"
    assert client.get("/api/v1/study-spaces/deletion-jobs").json()
    assert client.delete(f"/api/v1/providers/{pid}").status_code == 409
    # No uploader finally block executes. Only persisted leases and jobs remain.
    with client.app.state.session_factory() as db:
        for jid in (asset["job_id"], cleanup["id"]):
            db.get(MaterialJob, jid).lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    process(client, cleanup["id"])
    assert client.get("/api/v1/study-spaces/deletion-jobs").json() == []
    assert client.delete(f"/api/v1/providers/{pid}").status_code == 204

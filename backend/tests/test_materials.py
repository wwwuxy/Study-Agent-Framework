from pathlib import Path

import pytest
from conftest import provider, register, space

from app.knowledge.storage import MaterialStorage, validate_pdf
from app.providers.base import ProviderError
from app.providers.probe_pdf import make_probe_pdf


def test_pdf_validation_is_metadata_only_and_rejects_unsafe_files(tmp_path):
    sample = make_probe_pdf("CAPABILITY_PROBE_123")
    validate_pdf("book.pdf", "application/pdf", sample, 100000)
    for name, mime, data in [
        ("book.exe", "application/pdf", sample),
        ("book.pdf", "text/plain", sample),
        ("book.pdf", "application/pdf", b"not a PDF"),
        ("book.pdf", "application/pdf", sample + b"/JavaScript"),
    ]:
        with pytest.raises(ProviderError):
            validate_pdf(name, mime, data, 100000)
    with pytest.raises(ProviderError):
        validate_pdf("book.pdf", "application/pdf", sample, 10)
    storage = MaterialStorage(tmp_path)
    path = storage.save("user", "space", "asset", sample)
    assert Path(path).read_bytes() == sample
    assert Path(path).stat().st_mode & 0o777 == 0o600
    with pytest.raises(ProviderError):
        storage.path("../outside", "space", "asset")


def configure(client, embedding=False):
    register(client)
    response = client.post(
        "/api/v1/providers",
        json={
            "name": "文件演示",
            "provider_type": "fake_files",
            "chat_model": "demo",
            "api_key": "demo",
            "embedding_model": "demo-embedding" if embedding else None,
        },
    )
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    tested = client.post(f"/api/v1/providers/{pid}/test")
    assert tested.status_code == 200, tested.text
    assert tested.json()["file_input"] is True
    sid = space(client, pid)
    return pid, sid


def upload(client, sid, key="upload-1", consent=True, embedding=False):
    return client.post(
        f"/api/v1/study-spaces/{sid}/materials",
        content=make_probe_pdf("USER_MATERIAL"),
        headers={
            "Content-Type": "application/pdf",
            "X-Filename": "book.pdf",
            "Idempotency-Key": key,
            "X-File-Consent": str(consent).lower(),
            "X-Use-Embeddings": str(embedding).lower(),
        },
    )


def process(client, job_id):
    response = client.post(f"/api/v1/jobs/{job_id}/run")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "succeeded", response.text
    return response.json()


def test_upload_requires_explicit_consent_and_verified_file_capability(client):
    register(client)
    sid = space(client, provider(client))
    response = upload(client, sid)
    assert response.status_code == 422 and response.json()["error"]["code"] == "capability_not_supported"


def test_material_pipeline_search_citations_and_delete(client):
    _, sid = configure(client)
    root = f"/api/v1/study-spaces/{sid}"
    denied = upload(client, sid, consent=False)
    assert denied.status_code == 422
    response = upload(client, sid)
    assert response.status_code == 202, response.text
    uploaded = response.json()
    assert upload(client, sid).json()["id"] == uploaded["id"]
    process(client, uploaded["job_id"])
    asset = client.get(root + "/materials/" + uploaded["id"]).json()
    assert asset["status"] == "ready" and asset["sections"]
    assert all(s["locator_verified"] is False and s["locator"].get("page") is None for s in asset["sections"])
    results = client.post(root + "/materials/search", json={"query": "操作系统"}).json()
    assert results["mode"] == "keyword_llm_rerank" and results["results"]
    assert all(row["document_id"] == uploaded["id"] for row in results["results"])
    lesson = client.post(root + "/lessons", json={"idempotency_key": "material-lesson"}).json()
    assert lesson["citations"] and lesson["exercises"][0]["source_ids"]
    assert all(s["status"] == "unknown" for s in client.get(root + "/profile").json()["states"])
    response = client.delete(root + "/materials/" + uploaded["id"])
    assert response.status_code == 200, response.text
    process(client, response.json()["job_id"])
    assert client.get(root + "/materials/" + uploaded["id"]).status_code == 404
    assert client.post(root + "/materials/search", json={"query": "操作系统"}).json()["results"] == []
    assert client.get(root + "/lessons/current").json()["citations"] == []


def test_remote_embedding_and_reindex_do_not_change_learning_state(client):
    _, sid = configure(client, embedding=True)
    root = f"/api/v1/study-spaces/{sid}"
    response = upload(client, sid, embedding=True).json()
    process(client, response["job_id"])
    result = client.post(root + "/materials/search", json={"query": "内存管理", "mode": "embedding"})
    assert result.status_code == 200 and result.json()["mode"] == "remote_embedding"
    before = client.get(root + "/profile").json()
    indexed = client.post(
        root + f"/materials/{response['id']}/reindex",
        json={"idempotency_key": "reindex-1", "consent": True, "use_embeddings": False},
    )
    assert indexed.status_code == 202, indexed.text
    process(client, indexed.json()["job_id"])
    assert client.get(root + "/profile").json() == before


def test_material_and_job_are_user_isolated(client):
    _, sid = configure(client)
    response = upload(client, sid).json()
    client.post("/api/v1/auth/logout")
    register(client, "bob")
    for path in [
        f"/api/v1/jobs/{response['job_id']}",
        f"/api/v1/study-spaces/{sid}/materials/{response['id']}",
    ]:
        assert client.get(path).status_code == 404
    assert client.post(f"/api/v1/jobs/{response['job_id']}/run").status_code == 404


def test_cancelled_job_cannot_publish_material_index(client):
    _, sid = configure(client)
    response = upload(client, sid).json()
    assert client.post(f"/api/v1/jobs/{response['job_id']}/cancel").status_code == 200
    job = client.post(f"/api/v1/jobs/{response['job_id']}/run").json()
    assert job["status"] == "cancelled"
    assert (
        client.post(f"/api/v1/study-spaces/{sid}/materials/search", json={"query": "操作系统"}).json()[
            "results"
        ]
        == []
    )


def test_failed_section_resumes_without_reupload_or_reoutline(client):
    from app.providers.fake_files import FakeFileAdapter

    class FailingFile(FakeFileAdapter):
        uploads = outlines = 0
        failed = False

        async def upload_file(self, content, filename):
            self.uploads += 1
            return await super().upload_file(content, filename)

        async def analyze_file(self, ref, task):
            if task["schema"]["title"] == "RemoteOutline":
                self.outlines += 1
            elif not self.failed:
                self.failed = True
                raise ProviderError("provider_timeout", "可重试的超时")
            return await super().analyze_file(ref, task)

    _, sid = configure(client)
    adapter = FailingFile()
    client.app.state.adapter_factory = lambda _: adapter
    asset = upload(client, sid).json()
    failed = client.post("/api/v1/jobs/" + asset["job_id"] + "/run").json()
    assert failed["status"] == "failed"
    retry = client.post("/api/v1/jobs/" + asset["job_id"] + "/retry", json={"idempotency_key": "retry-one"})
    assert retry.status_code == 202
    process(client, retry.json()["id"])
    assert adapter.uploads == adapter.outlines == 1
    assert (
        client.post(
            "/api/v1/jobs/" + asset["job_id"] + "/retry", json={"idempotency_key": "retry-one"}
        ).json()["id"]
        == retry.json()["id"]
    )


def test_invalid_remote_schema_never_publishes_and_audits_error(client):
    from app.providers.fake_files import FakeFileAdapter

    class BadFile(FakeFileAdapter):
        async def analyze_file(self, ref, task):
            return {"untrusted": "wrong schema"}

    _, sid = configure(client)
    client.app.state.adapter_factory = lambda _: BadFile()
    asset = upload(client, sid).json()
    result = client.post("/api/v1/jobs/" + asset["job_id"] + "/run").json()
    assert result["status"] == "failed"
    assert result["error_code"] == "invalid_structured_output"
    assert client.get(f"/api/v1/study-spaces/{sid}/materials/{asset['id']}").json()["sections"] == []
    runs = client.get(f"/api/v1/study-spaces/{sid}/runs").json()
    assert any(r["error_code"] == "invalid_structured_output" for r in runs)


def test_cancel_during_remote_upload_preserves_cleanup_handle(client):
    from sqlalchemy import select

    from app.db.models import MaterialAsset, MaterialJob
    from app.providers.fake_files import FakeFileAdapter

    class CancelDuringUpload(FakeFileAdapter):
        async def upload_file(self, content, filename):
            with client.app.state.session_factory() as db:
                asset = db.scalar(select(MaterialAsset).where(MaterialAsset.space_id == sid))
                asset.status, asset.generation = "deleting", asset.generation + 1
                job = db.scalar(select(MaterialJob).where(MaterialJob.asset_id == asset.id))
                job.status = "cancelled"
                db.commit()
            return "demo-late-file"

    _, sid = configure(client)
    client.app.state.adapter_factory = lambda _: CancelDuringUpload()
    asset = upload(client, sid).json()
    assert client.post("/api/v1/jobs/" + asset["job_id"] + "/run").json()["status"] == "cancelled"
    rows = client.get(f"/api/v1/study-spaces/{sid}/materials").json()
    assert rows[0]["job"]["kind"] == "cleanup"
    process(client, rows[0]["job_id"])
    assert client.get(f"/api/v1/study-spaces/{sid}/materials").json() == []


def test_reindex_completed_request_can_be_replayed_and_conflicts_rejected(client):
    _, sid = configure(client)
    asset = upload(client, sid).json()
    process(client, asset["job_id"])
    path = f"/api/v1/study-spaces/{sid}/materials/{asset['id']}/reindex"
    body = {"idempotency_key": "same-reindex", "consent": True, "use_embeddings": False}
    response = client.post(path, json=body).json()
    process(client, response["job_id"])
    assert client.post(path, json=body).json()["job_id"] == response["job_id"]
    assert client.post(path, json={**body, "use_embeddings": True}).status_code == 409


def test_cleanup_credential_rotation_remains_visible_and_protected(client):
    pid, sid = configure(client)
    asset = upload(client, sid).json()
    process(client, asset["job_id"])
    client.patch("/api/v1/providers/" + pid, json={"api_key": "new-key"})
    removed = client.delete(f"/api/v1/study-spaces/{sid}/materials/{asset['id']}").json()
    failed = client.post("/api/v1/jobs/" + removed["job_id"] + "/run").json()
    assert failed["status"] == "failed" and failed["error_code"] == "remote_cleanup_required"
    rows = client.get(f"/api/v1/study-spaces/{sid}/materials").json()
    assert rows[0]["warning"] and rows[0]["status"] == "deleting"
    assert client.get(f"/api/v1/study-spaces/{sid}/materials/{asset['id']}/download").status_code == 404


def test_exhausted_expired_job_is_failed_instead_of_stuck(client):
    from datetime import timedelta

    from app.db.models import MaterialJob, utcnow

    _, sid = configure(client)
    asset = upload(client, sid).json()
    with client.app.state.session_factory() as db:
        job = db.get(MaterialJob, asset["job_id"])
        job.status, job.attempts, job.lease_until = "running", 3, utcnow() - timedelta(seconds=1)
        db.commit()
    result = client.post("/api/v1/jobs/" + asset["job_id"] + "/run").json()
    assert result["status"] == "failed" and result["error_code"] == "job_attempts_exhausted"


def test_source_first_insufficient_evidence_requires_opt_in(client):
    from app.db.models import StudySpace

    _, sid = configure(client)
    asset = upload(client, sid).json()
    process(client, asset["job_id"])
    with client.app.state.session_factory() as db:
        db.get(StudySpace, sid).goal = "quantum cosmology"
        db.commit()
    path = f"/api/v1/study-spaces/{sid}"
    denied = client.post(path + "/diagnostics")
    assert denied.status_code == 422 and denied.json()["error"]["code"] == "insufficient_material_evidence"
    assert client.patch(path, json={"allow_general_knowledge": True}).status_code == 200
    assert client.post(path + "/diagnostics").status_code == 200


def test_fabricated_source_cannot_be_published(client):
    from app.providers.fake_files import FakeFileAdapter

    class ForgedSource(FakeFileAdapter):
        async def generate_structured(self, messages, schema):
            result = await super().generate_structured(messages, schema)
            if schema.get("title") == "LessonContent":
                result["source_ids"] = ["another-user-section"]
            return result

    _, sid = configure(client)
    asset = upload(client, sid).json()
    process(client, asset["job_id"])
    client.app.state.adapter_factory = lambda _: ForgedSource()
    path = f"/api/v1/study-spaces/{sid}"
    response = client.post(path + "/lessons", json={"idempotency_key": "forged"})
    assert response.status_code == 502 and response.json()["error"]["code"] == "invalid_citation"
    assert client.get(path + "/lessons/current").json() is None


def test_upload_rejects_missing_idempotency_key_without_server_error(client):
    _, sid = configure(client)
    result = client.post(
        f"/api/v1/study-spaces/{sid}/materials",
        content=make_probe_pdf("a"),
        headers={"Content-Type": "application/pdf", "X-Filename": "a.pdf", "X-File-Consent": "true"},
    )
    assert result.status_code == 422 and result.json()["error"]["code"] == "invalid_idempotency_key"


def test_provider_change_during_upload_stops_before_next_remote_call(client):
    from app.db.models import ProviderConfig
    from app.providers.fake_files import FakeFileAdapter

    pid, sid = configure(client)
    calls = []

    class Changing(FakeFileAdapter):
        async def upload_file(self, content, filename):
            with client.app.state.session_factory() as db:
                config = db.get(ProviderConfig, pid)
                config.chat_model, config.tested, config.capabilities = "changed-model", False, {}
                db.commit()
            return "original-file-ref"

        async def analyze_file(self, ref, task):
            calls.append(task)
            return await super().analyze_file(ref, task)

    client.app.state.adapter_factory = lambda _: Changing()
    asset = upload(client, sid).json()
    result = client.post("/api/v1/jobs/" + asset["job_id"] + "/run").json()
    assert calls == [] and result["error_code"] == "provider_config_changed"


def test_old_provider_cannot_be_removed_while_remote_handle_still_needs_it(client):
    pid, sid = configure(client)
    asset = upload(client, sid).json()
    process(client, asset["job_id"])
    second = client.post(
        "/api/v1/providers",
        json={"name": "another", "provider_type": "fake_files", "chat_model": "demo", "api_key": "demo"},
    ).json()["id"]
    client.post("/api/v1/providers/" + second + "/test")
    client.patch(f"/api/v1/study-spaces/{sid}", json={"provider_id": second})
    result = client.post(
        f"/api/v1/study-spaces/{sid}/materials/{asset['id']}/reindex",
        json={"idempotency_key": "switch", "consent": True},
    ).json()
    process(client, result["job_id"])
    assert client.delete("/api/v1/providers/" + pid).status_code == 409
    removed = client.delete(f"/api/v1/study-spaces/{sid}/materials/{asset['id']}").json()
    process(client, removed["job_id"])
    assert client.delete("/api/v1/providers/" + pid).status_code == 204


def test_delete_at_final_publication_cannot_resurrect_index(client, monkeypatch):
    from app.db.models import MaterialAsset, MaterialJob
    from app.jobs import materials as jobs

    _, sid = configure(client)
    asset = upload(client, sid).json()
    original = jobs.config_for
    deleted = False

    def concurrent_delete(db, current_asset):
        nonlocal deleted
        config = original(db, current_asset)
        current_job = db.get(MaterialJob, asset["job_id"])
        if current_job.data.get("sections") and not deleted:
            deleted = True
            with client.app.state.session_factory() as other:
                row = other.get(MaterialAsset, asset["id"])
                row.generation, row.status = row.generation + 1, "deleting"
                other.get(MaterialJob, asset["job_id"]).status = "cancelled"
                other.commit()
        return config

    monkeypatch.setattr(jobs, "config_for", concurrent_delete)
    result = client.post("/api/v1/jobs/" + asset["job_id"] + "/run").json()
    assert deleted and result["status"] == "cancelled"
    assert client.get(f"/api/v1/study-spaces/{sid}/materials/{asset['id']}").status_code == 404
    assert (
        client.post(f"/api/v1/study-spaces/{sid}/materials/search", json={"query": "操作系统"}).json()[
            "results"
        ]
        == []
    )


def test_late_upload_after_completed_deletion_keeps_failed_cleanup_visible(client):
    from sqlalchemy import select

    from app.db.models import MaterialAsset, MaterialJob
    from app.providers.fake_files import FakeFileAdapter

    _, sid = configure(client)

    class LateUpload(FakeFileAdapter):
        async def upload_file(self, content, filename):
            # Another worker already finished deletion while this request was in flight.
            with client.app.state.session_factory() as db:
                asset = db.scalar(select(MaterialAsset).where(MaterialAsset.space_id == sid))
                asset.status, asset.generation = "deleted", asset.generation + 1
                job = db.scalar(select(MaterialJob).where(MaterialJob.asset_id == asset.id))
                job.status = "cancelled"
                db.commit()
            return "late-remote-file"

        async def delete_file(self, ref):
            raise ProviderError("provider_unavailable", "远端删除暂时失败，请重试")

    client.app.state.adapter_factory = lambda _: LateUpload()
    asset = upload(client, sid).json()
    client.post("/api/v1/jobs/" + asset["job_id"] + "/run")
    rows = client.get(f"/api/v1/study-spaces/{sid}/materials").json()
    assert len(rows) == 1 and rows[0]["status"] == "deleting"
    cleanup = client.post("/api/v1/jobs/" + rows[0]["job_id"] + "/run").json()
    assert cleanup["status"] == "failed"
    rows = client.get(f"/api/v1/study-spaces/{sid}/materials").json()
    assert len(rows) == 1 and rows[0]["warning"] and rows[0]["job"]["status"] == "failed"


def test_material_publication_updates_saved_plan_for_new_concepts(client):
    from app.core.orchestrator import append_event, rebuild_states, save_plan
    from app.db.models import StudySpace
    from app.providers.fake_files import FakeFileAdapter

    _, sid = configure(client)
    root = f"/api/v1/study-spaces/{sid}"
    with client.app.state.session_factory() as db:
        current_space = db.get(StudySpace, sid)
        for concept in client.get(root + "/concepts").json():
            for index in range(2):
                append_event(
                    db,
                    current_space,
                    "assessment_submitted",
                    f"prior-{concept['key']}-{index}",
                    {
                        "assessment_item_id": f"item-{concept['key']}-{index}",
                        "concept_ids": [concept["key"]],
                        "is_correct": True,
                        "confidence": "high",
                        "assistance_level": "none",
                        "difficulty": 2,
                        "evaluator": "deterministic_answer_key",
                        "misconceptions": [],
                    },
                )
        rebuild_states(db, current_space)
        save_plan(db, current_space)
        db.commit()
    assert client.get(root + "/plan").json()["next_action"]["action"] == "ASSESS"
    before_events = client.get(root + "/events").json()

    class NewConceptFile(FakeFileAdapter):
        async def analyze_file(self, ref, task):
            result = await super().analyze_file(ref, task)
            if task["schema"]["title"] == "RemoteSection":
                result["concepts"] = ["虚拟内存分页"]
            return result

    client.app.state.adapter_factory = lambda _: NewConceptFile()
    asset = upload(client, sid).json()
    process(client, asset["job_id"])
    live_action = client.get(root + "/next-action").json()
    assert live_action["action"] == "DIAGNOSE" and live_action["concept_ids"][0].startswith("mat_")
    assert client.get(root + "/plan").json()["next_action"] == live_action
    states = client.get(root + "/profile").json()["states"]
    assert all(s["status"] == "mastered" for s in states if not s["concept_id"].startswith("mat_"))
    assert next(s for s in states if s["concept_id"].startswith("mat_"))["evidence_count"] == 0
    assert client.get(root + "/events").json() == before_events


def test_upload_automatically_commits_metadata_status_and_knowledge(settings, monkeypatch):
    import asyncio
    import hashlib
    import threading
    import time

    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from app.db.models import KnowledgeConcept, MaterialAsset, MaterialJob, MaterialSection
    from app.main import create_app
    from app.providers.fake_files import FakeFileAdapter

    started, release = threading.Event(), threading.Event()

    class AutomaticFile(FakeFileAdapter):
        async def upload_file(self, content, filename):
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            return await super().upload_file(content, filename)

        async def analyze_file(self, ref, task):
            result = await super().analyze_file(ref, task)
            if task["schema"]["title"] == "RemoteSection":
                result["concepts"] = ["虚拟内存分页"]
            return result

    settings.material_worker_enabled = True
    app = create_app(settings, adapter_factory=lambda _: AutomaticFile())
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    with TestClient(app) as automatic:
        _, sid = configure(automatic)
        response = upload(automatic, sid)
        assert response.status_code == 202
        asset_id = response.json()["id"]
        try:
            assert started.wait(5), "后台未自动领取上传任务"
            with app.state.session_factory() as db:
                asset = db.get(MaterialAsset, asset_id)
                job = db.get(MaterialJob, response.json()["job_id"])
                assert asset.filename == "book.pdf"
                assert asset.sha256 == hashlib.sha256(make_probe_pdf("USER_MATERIAL")).hexdigest()
                assert job.status == "running" and asset.status == "indexing"
                assert db.scalar(select(func.count()).select_from(MaterialSection)) == 0
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = automatic.get(f"/api/v1/study-spaces/{sid}/materials/{asset_id}").json()
            if result["status"] in {"ready", "failed"}:
                break
            time.sleep(0.02)
        assert result["status"] == "ready" and result["sections"]
        with app.state.session_factory() as db:
            assert (
                db.scalar(select(MaterialJob.status).where(MaterialJob.id == response.json()["job_id"]))
                == "succeeded"
            )
            assert (
                db.scalar(
                    select(KnowledgeConcept).where(
                        KnowledgeConcept.space_id == sid,
                        KnowledgeConcept.data["name"].as_string() == "虚拟内存分页",
                    )
                )
                is not None
            )
        assert all(
            s["status"] == "unknown"
            for s in automatic.get(f"/api/v1/study-spaces/{sid}/profile").json()["states"]
        )
        assert upload(automatic, sid).json()["id"] == asset_id
        with app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(MaterialAsset)) == 1
            assert db.scalar(select(func.count()).select_from(MaterialJob)) == 1
    # Another app instance reads committed results after the worker and original connection close.
    with TestClient(create_app(settings)) as restarted:
        assert (
            restarted.post(
                "/api/v1/auth/login", json={"username": "alice", "password": "strong-password-2026"}
            ).status_code
            == 200
        )
        persisted = restarted.get(f"/api/v1/study-spaces/{sid}/materials/{asset_id}").json()
        assert persisted["status"] == "ready" and persisted["sections"]


def test_publication_does_not_overwrite_concurrent_answer(client, monkeypatch, settings):
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL row-lock race; SQLite serializes database writers")
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import select

    from app.core import orchestrator
    from app.db.models import StudySpace, User

    _, sid = configure(client)
    root = f"/api/v1/study-spaces/{sid}"
    target = client.get(root + "/concepts").json()[0]["key"]
    asset = upload(client, sid).json()
    original = orchestrator.event_data
    attempted, committed = threading.Event(), threading.Event()
    future = None

    def submit_answer():
        with client.app.state.session_factory() as other:
            space = other.get(StudySpace, sid)
            attempted.set()
            # Same user lock as current_user in the authenticated answer endpoint.
            other.scalar(select(User).where(User.id == space.user_id).with_for_update())
            orchestrator.append_event(
                other,
                space,
                "assessment_submitted",
                "concurrent-answer",
                {
                    "assessment_item_id": "concurrent-item",
                    "concept_ids": [target],
                    "is_correct": True,
                    "confidence": "high",
                    "assistance_level": "none",
                    "difficulty": 2,
                    "evaluator": "deterministic_answer_key",
                    "misconceptions": [],
                },
            )
            orchestrator.rebuild_states(other, space)
            orchestrator.save_plan(other, space)
            other.commit()
            committed.set()

    with ThreadPoolExecutor(max_workers=1) as pool:

        def after_read(db, space_id):
            nonlocal future
            events = original(db, space_id)
            if future is None:
                # Mark before dispatch so event_data in the answer cannot dispatch again.
                future = False
                future = pool.submit(submit_answer)
                assert attempted.wait(5)
                # Without the shared lock, the answer commits before the stale replay resumes.
                committed.wait(0.5)
            return events

        monkeypatch.setattr(orchestrator, "event_data", after_read)
        process(client, asset["job_id"])
        future.result(timeout=10)
    actual = next(s for s in client.get(root + "/profile").json()["states"] if s["concept_id"] == target)
    assert actual["evidence_count"] == 1 and actual["status"] == "learning"
    assert client.get(root + "/plan").json()["next_action"] == client.get(root + "/next-action").json()

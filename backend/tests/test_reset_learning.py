import asyncio

from conftest import provider, register, space
from sqlalchemy import select

from app.db.models import LearningEvent, ProviderConfig, ReviewState, StudySpace, User


def test_reset_preserves_accounts_configs_and_never_erases_new_spaces_on_retry(client, settings):
    from app.maintenance.reset_learning import reset_learning

    register(client)
    pid = provider(client)
    sid = space(client, pid)
    root = f"/api/v1/study-spaces/{sid}"
    q = client.post(root + "/diagnostics").json()["items"][0]
    client.post(root + "/attempts", json={"item_id": q["id"], "answer": "A", "idempotency_key": "answer"})
    with client.app.state.session_factory() as db:
        uid = db.get(StudySpace, sid).user_id
        password, encrypted = db.get(User, uid).password_hash, db.get(ProviderConfig, pid).encrypted_api_key
    preview = asyncio.run(reset_learning(settings, "m3-reset", apply=False, expected_target=None))
    assert preview["spaces"] == 1
    assert client.get(root).status_code == 200
    result = asyncio.run(
        reset_learning(settings, "m3-reset", apply=True, expected_target=preview["fingerprint"])
    )
    assert result["spaces_erased"] == 1 and result["remote_pending"] == 0
    assert client.get("/api/v1/study-spaces").json() == []
    with client.app.state.session_factory() as db:
        assert db.get(User, uid).password_hash == password
        assert db.get(ProviderConfig, pid).encrypted_api_key == encrypted
        assert not db.scalars(select(LearningEvent)).all()
        assert not db.scalars(select(ReviewState)).all()
    new_sid = space(client, pid, key="new-after-reset")
    assert (
        asyncio.run(reset_learning(settings, "m3-reset", apply=True, expected_target=preview["fingerprint"]))
        == result
    )
    assert client.get(f"/api/v1/study-spaces/{new_sid}").status_code == 200


def test_reset_wrong_target_cannot_modify_data(client, settings):
    import pytest

    from app.maintenance.reset_learning import reset_learning

    register(client)
    sid = space(client, provider(client))
    with pytest.raises(ValueError, match="目标"):
        asyncio.run(reset_learning(settings, "bad-target", apply=True, expected_target="wrong"))
    assert client.get(f"/api/v1/study-spaces/{sid}").status_code == 200


def test_completed_reset_recovers_marker_left_by_crash(client, settings):
    from app.maintenance.reset_learning import maintenance_marker, reset_learning

    register(client)
    pid = provider(client)
    space(client, pid)
    preview = asyncio.run(reset_learning(settings, "crash-after-commit"))
    result = asyncio.run(
        reset_learning(settings, "crash-after-commit", apply=True, expected_target=preview["fingerprint"])
    )
    marker = maintenance_marker(settings)
    marker.write_text("crash-after-commit")
    assert (
        asyncio.run(
            reset_learning(settings, "crash-after-commit", apply=True, expected_target=preview["fingerprint"])
        )
        == result
    )
    assert not marker.exists()
    assert space(client, pid, "after-recovery")


def test_reset_keeps_retryable_remote_cleanup_without_user_learning_text(client, settings, monkeypatch):
    from test_materials import configure, process, upload

    from app.db.models import MaterialAsset, MaterialJob
    from app.maintenance.reset_learning import reset_learning
    from app.providers.base import ProviderError
    from app.providers.fake_files import FakeFileAdapter

    _, sid = configure(client)
    asset = upload(client, sid).json()
    process(client, asset["job_id"])

    async def fail(self, ref):
        raise ProviderError("provider_unavailable", "delete unavailable")

    monkeypatch.setattr(FakeFileAdapter, "delete_file", fail)
    preview = asyncio.run(reset_learning(settings, "remote-reset", apply=False, expected_target=None))
    result = asyncio.run(
        reset_learning(settings, "remote-reset", apply=True, expected_target=preview["fingerprint"])
    )
    assert result["remote_pending"] == 1
    assert client.get("/api/v1/study-spaces").json() == []
    with client.app.state.session_factory() as db:
        row = db.get(MaterialAsset, asset["id"])
        assert row.filename == "" and row.remote_files
        assert any(
            j.status == "failed" for j in db.scalars(select(MaterialJob).where(MaterialJob.kind == "cleanup"))
        )

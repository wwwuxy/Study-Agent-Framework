import hashlib
from pathlib import Path

import pytest
from test_materials import configure, process, upload

from app.knowledge.storage import MaterialStorage
from app.providers.base import ProviderError
from app.providers.probe_pdf import make_probe_pdf


def forbidden_whole_read(*args, **kwargs):
    raise AssertionError("material transfers must not read an entire file into memory")


@pytest.mark.asyncio
async def test_staged_upload_writes_before_consuming_entire_stream_and_publishes_atomically(tmp_path):
    storage = MaterialStorage(tmp_path)
    sample = make_probe_pdf("STREAMING")
    final = storage.path("user", "space", "asset")

    async def chunks():
        yield sample[:20]
        staged_files = list(final.parent.glob("*.part"))
        assert len(staged_files) == 1
        assert staged_files[0].stat().st_size == 20
        assert not final.exists()
        yield sample[20:]

    with storage.stage("user", "space", "asset", "book.pdf", "application/pdf", 100000) as staged:
        await staged.receive(chunks())
        assert staged.size_bytes == len(sample)
        assert staged.sha256 == hashlib.sha256(sample).hexdigest()
        assert not final.exists()
        staged.publish()
        assert final.read_bytes() == sample
        assert final.stat().st_mode & 0o777 == 0o600
        staged.keep()
    assert final.read_bytes() == sample
    assert not list(final.parent.glob("*.part"))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["limit", "unsafe", "disconnect", "invalid", "database"])
async def test_staging_removes_partial_and_uncommitted_files(tmp_path, failure):
    storage = MaterialStorage(tmp_path)
    sample = make_probe_pdf("CLEANUP")

    async def chunks():
        yield sample
        if failure == "unsafe":
            yield b"/Java"
            yield b"Script"
        elif failure == "disconnect":
            raise ConnectionError("client disconnected")
        elif failure == "limit":
            yield b"x"

    with pytest.raises((ProviderError, ConnectionError, RuntimeError)):
        with storage.stage(
            "user",
            "space",
            "asset",
            "book.pdf",
            "application/pdf",
            len(sample) + (100 if failure == "unsafe" else 0),
        ) as staged:
            if failure == "invalid":

                async def invalid():
                    yield b"%PDF-incomplete"

                await staged.receive(invalid())
            else:
                await staged.receive(chunks())
            staged.publish()
            if failure == "database":
                raise RuntimeError("database commit failed")
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("*.bin"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "signature", [b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/OpenAction", b"/RichMedia"]
)
async def test_pdf_safety_signatures_cannot_be_hidden_across_stream_chunks(tmp_path, signature):
    sample = make_probe_pdf("SIGNATURE")
    storage = MaterialStorage(tmp_path)

    async def chunks():
        yield sample
        for value in signature:
            yield bytes([value])

    with pytest.raises(ProviderError) as error:
        with storage.stage("user", "space", "asset", "book.pdf", "application/pdf", 100000) as staged:
            await staged.receive(chunks())
    assert error.value.code == "unsafe_file"
    assert not list(tmp_path.rglob("*.part"))


def test_worker_forwards_a_file_stream_and_closes_it(client, monkeypatch):
    from app.providers.fake_files import FakeFileAdapter

    handles = []
    sample = make_probe_pdf("USER_MATERIAL")

    class StreamingFile(FakeFileAdapter):
        async def upload_file(self, content, filename):
            assert hasattr(content, "read"), "worker must forward an open file, not bytes"
            assert not content.closed
            assert filename == "book.pdf"
            handles.append(content)
            assert content.read(10) == sample[:10]
            assert content.read(65536) == sample[10:]
            return "streamed-file"

    _, sid = configure(client)
    client.app.state.adapter_factory = lambda _: StreamingFile()
    asset = upload(client, sid).json()
    monkeypatch.setattr(Path, "read_bytes", forbidden_whole_read)
    monkeypatch.setattr(MaterialStorage, "read", forbidden_whole_read)
    process(client, asset["job_id"])
    assert handles and all(handle.closed for handle in handles)


def test_repeated_upload_and_conflicts_do_not_leak_staging_files(client, settings):
    _, sid = configure(client)
    first = upload(client, sid).json()
    assert upload(client, sid).json()["id"] == first["id"]
    response = client.post(
        f"/api/v1/study-spaces/{sid}/materials",
        content=make_probe_pdf("DIFFERENT"),
        headers={
            "Content-Type": "application/pdf",
            "X-Filename": "book.pdf",
            "X-File-Consent": "true",
            "Idempotency-Key": "upload-1",
        },
    )
    assert response.status_code == 409
    assert not list(Path(settings.material_storage_dir).rglob("*.part"))
    assert len(list(Path(settings.material_storage_dir).rglob("*.bin"))) == 1


@pytest.mark.asyncio
async def test_http_upload_streams_unknown_length_body_and_cleans_oversize_request(
    client, settings, monkeypatch
):
    import httpx

    _, sid = configure(client)
    sample = make_probe_pdf("HTTP_CHUNKS")
    directory = Path(settings.material_storage_dir)
    headers = {
        "Content-Type": "application/pdf",
        "X-Filename": "book.pdf",
        "X-File-Consent": "true",
        "Idempotency-Key": "streamed-http",
    }

    async def chunks():
        yield sample[:3]  # Header itself can span incoming chunks.
        assert len(list(directory.rglob("*.part"))) == 1
        assert list(directory.rglob("*.part"))[0].stat().st_size == 3
        yield sample[3:-3]
        yield sample[-3:]  # EOF marker can also span chunks.

    transport = httpx.ASGITransport(app=client.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies=dict(client.cookies.items())
    ) as remote:
        result = await remote.post(f"/api/v1/study-spaces/{sid}/materials", content=chunks(), headers=headers)
        assert result.status_code == 202, result.text
        assert result.json()["size_bytes"] == len(sample)
        monkeypatch.setattr(settings, "material_max_bytes", len(sample) - 1)
        result = await remote.post(
            f"/api/v1/study-spaces/{sid}/materials",
            content=chunks(),
            headers={**headers, "Idempotency-Key": "over-limit"},
        )
        assert result.status_code == 413
    assert not list(directory.rglob("*.part"))
    assert len(list(directory.rglob("*.bin"))) == 1


def test_database_failure_after_publication_removes_original_and_metadata(client, settings, monkeypatch):
    from app.api import materials

    _, sid = configure(client)

    def failed_job(*args, **kwargs):
        raise RuntimeError("cannot create persistent job")

    monkeypatch.setattr(materials, "new_job", failed_job)
    with pytest.raises(RuntimeError, match="cannot create persistent job"):
        upload(client, sid)
    directory = Path(settings.material_storage_dir)
    assert not list(directory.rglob("*.part"))
    assert not list(directory.rglob("*.bin"))
    assert client.get(f"/api/v1/study-spaces/{sid}/materials").json() == []


@pytest.mark.asyncio
async def test_large_generated_upload_has_bounded_python_memory(tmp_path):
    import tracemalloc

    storage = MaterialStorage(tmp_path)
    block = b"x" * 65536
    count = 1024  # 64 MiB of generated content, without a 64 MiB input buffer.

    async def chunks():
        yield b"%PDF-1.4\n"
        for _ in range(count):
            yield block
        yield b"\n%%EOF"

    tracemalloc.start()
    try:
        with storage.stage("user", "space", "large", "book.pdf", "application/pdf", 100_000_000) as staged:
            await staged.receive(chunks())
            assert staged.size_bytes == 67_108_879
            _, peak = tracemalloc.get_traced_memory()
            assert peak < 8 * 1024 * 1024, f"buffering scales with file size: peak={peak}"
    finally:
        tracemalloc.stop()
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.asyncio
async def test_staging_cleans_temp_file_even_when_disk_close_fails(tmp_path):
    storage = MaterialStorage(tmp_path)

    class FailingClose:
        def __init__(self, file):
            self.file = file

        def __getattr__(self, name):
            return getattr(self.file, name)

        def close(self):
            self.file.close()
            raise OSError("disk flush failed")

    async def chunks():
        yield make_probe_pdf("DISK_ERROR")

    with pytest.raises(OSError, match="disk flush failed"):
        with storage.stage("user", "space", "asset", "book.pdf", "application/pdf", 100000) as staged:
            staged.file = FailingClose(staged.file)
            await staged.receive(chunks())
    assert not list(tmp_path.rglob("*.part"))

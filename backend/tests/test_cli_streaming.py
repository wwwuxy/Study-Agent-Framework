import httpx
import pytest

from app.cli.client import APIClient
from app.cli.errors import CLIError
from app.cli.state import StateStore


@pytest.mark.parametrize("failure", [None, "timeout", "disconnect"])
def test_download_writes_as_chunks_arrive_and_removes_partial_on_error(tmp_path, failure):
    output = tmp_path / "book.pdf"
    first = b"%PDF-1.4\n" + b"x" * (65536 - 9)

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield first
            assert output.exists(), "must create destination before consuming response"
            assert output.stat().st_mode & 0o777 == 0o600
            assert output.stat().st_size == len(first), "must write before receiving the next chunk"
            if failure == "timeout":
                raise httpx.ReadTimeout("slow download")
            if failure == "disconnect":
                raise httpx.ReadError("connection lost")
            yield b"%%EOF"

    def handle(request):
        return httpx.Response(200, stream=Stream())

    client = APIClient(
        "http://localhost:8000", StateStore(tmp_path / "cli"), transport=httpx.MockTransport(handle)
    )
    try:
        if failure:
            with pytest.raises(CLIError) as error:
                client.download("/material/download", output)
            assert error.value.code == ("request_timeout" if failure == "timeout" else "connection_failed")
            assert not output.exists()
        else:
            client.download("/material/download", output)
            assert output.read_bytes() == first + b"%%EOF"
    finally:
        client.close()


def test_download_does_not_replace_existing_file_or_write_error_response(tmp_path):
    output = tmp_path / "existing.pdf"
    output.write_bytes(b"original")
    client = APIClient(
        "http://localhost:8000",
        StateStore(tmp_path / "cli"),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"new")),
    )
    try:
        with pytest.raises(CLIError) as error:
            client.download("/file", output)
        assert error.value.code == "output_exists"
        assert output.read_bytes() == b"original"
    finally:
        client.close()
    client = APIClient(
        "http://localhost:8000",
        StateStore(tmp_path / "cli"),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(404, json={"error": {"code": "not_found", "message": "missing file"}})
        ),
    )
    try:
        missing = tmp_path / "missing.pdf"
        with pytest.raises(CLIError) as error:
            client.download("/file", missing)
        assert error.value.code == "not_found"
        assert not missing.exists()
    finally:
        client.close()

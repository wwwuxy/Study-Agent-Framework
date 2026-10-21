"""Size-boundary checks without allocating or transferring GiB-sized payloads."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.cli.errors import CLIError
from app.cli.main import build_parser, execute
from app.core.settings import Settings


def test_material_limit_can_be_configured_to_one_gib():
    settings = Settings(_env_file=None, material_max_bytes=1_073_741_824)
    assert settings.material_max_bytes == 1_073_741_824


def test_material_limit_rejects_more_than_one_gib():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, material_max_bytes=1_073_741_825)


@pytest.mark.parametrize("size", [51_380_224, 1_073_741_824])
def test_cli_upload_accepts_files_above_old_limit_through_one_gib(tmp_path, monkeypatch, size):
    path = tmp_path / "large.pdf"
    with path.open("wb") as file:
        file.write(b"%PDF-1.4\n%%EOF")
        file.truncate(size)  # Sparse file: real stat without allocating a GiB.
    uploads = []

    def forbidden(*args, **kwargs):
        raise AssertionError("CLI upload must stream rather than call read_bytes")

    def upload(method, url, **kwargs):
        source = kwargs["content"]
        assert hasattr(source, "read") and not source.closed
        assert source.read(14) == b"%PDF-1.4\n%%EOF"
        assert kwargs["headers"]["Content-Length"] == str(size)
        uploads.append((method, url, kwargs))
        return {"id": "accepted-material"}

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    args = build_parser().parse_args(["material", "upload", str(path), "--accept-file-transfer"])
    client = SimpleNamespace(active_space=lambda _: "/study-spaces/owned", request=upload)
    result = execute(args, client, None, None, False, None)
    assert result == {"id": "accepted-material"}
    assert len(uploads) == 1
    method, url, kwargs = uploads[0]
    assert (method, url) == ("POST", "/study-spaces/owned/materials")
    assert kwargs["content"].closed
    assert kwargs["headers"]["X-File-Consent"] == "true"


def test_cli_upload_rejects_more_than_one_gib_before_reading(tmp_path, monkeypatch):
    path = tmp_path / "too-large.pdf"
    with path.open("wb") as file:
        file.truncate(1_073_741_825)

    def forbidden(*args, **kwargs):
        pytest.fail("oversized files must be rejected before reading or sending bytes")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    args = build_parser().parse_args(["material", "upload", str(path), "--accept-file-transfer"])
    client = SimpleNamespace(active_space=lambda _: "/study-spaces/owned", request=forbidden)
    with pytest.raises(CLIError) as error:
        execute(args, client, None, None, False, None)
    assert error.value.code == "file_too_large"
    assert "1024 MiB" in error.value.message

import hashlib
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.providers.base import ProviderError

STREAM_CHUNK_BYTES = 64 * 1024
UNSAFE_PDF_SIGNATURES = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/OpenAction", b"/RichMedia")


class PDFStreamValidator:
    """Bounded byte-signature checks and hashing, never document extraction."""

    def __init__(self, filename, mime, max_bytes):
        if (
            not filename
            or len(filename) > 200
            or "/" in filename
            or "\\" in filename
            or any(ord(c) < 32 or ord(c) == 127 for c in filename)
            or not filename.lower().endswith(".pdf")
            or mime.split(";")[0] != "application/pdf"
        ):
            raise ProviderError("unsupported_file_type", "当前适配器仅支持经过能力检测的 PDF 文件", 422)
        self.max_bytes = max_bytes
        self.size_bytes = 0
        self.header = b""
        self.tail = b""
        self.overlap = b""
        self.hash = hashlib.sha256()

    def update(self, chunk):
        self.size_bytes += len(chunk)
        if self.size_bytes > self.max_bytes:
            raise ProviderError("file_too_large", "文件超过本服务的上传大小限制", 413)
        self.header += chunk[: 5 - len(self.header)]
        scan = self.overlap + chunk
        if any(signature in scan for signature in UNSAFE_PDF_SIGNATURES):
            raise ProviderError(
                "unsafe_file", "文件包含主动内容或嵌入内容标识，请提供不含这些内容的 PDF", 422
            )
        self.overlap = scan[-(max(map(len, UNSAFE_PDF_SIGNATURES)) - 1) :]
        self.tail = (self.tail + chunk)[-2048:]
        self.hash.update(chunk)

    def finish(self):
        if self.header != b"%PDF-" or b"%%EOF" not in self.tail:
            raise ProviderError("invalid_file", "文件格式标识与 PDF 不符或文件不完整", 422)


def validate_pdf(filename, mime, data, max_bytes):
    validator = PDFStreamValidator(filename, mime, max_bytes)
    for start in range(0, len(data), STREAM_CHUNK_BYTES):
        validator.update(data[start : start + STREAM_CHUNK_BYTES])
    validator.finish()


class StagedMaterial:
    def __init__(self, path, validator):
        self.path = path
        self.validator = validator
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".upload-", suffix=".part", dir=path.parent)
        self.temp_path = Path(name)
        self.file = os.fdopen(fd, "wb")
        self.published = False
        self.committed = False

    @property
    def size_bytes(self):
        return self.validator.size_bytes

    @property
    def sha256(self):
        return self.validator.hash.hexdigest()

    def _write(self, chunk):
        self.validator.update(chunk)
        self.file.write(chunk)
        self.file.flush()

    async def receive(self, chunks):
        async for chunk in chunks:
            view = memoryview(chunk)
            for start in range(0, len(view), STREAM_CHUNK_BYTES):
                await run_in_threadpool(self._write, bytes(view[start : start + STREAM_CHUNK_BYTES]))
        self.validator.finish()
        self.file.close()

    def publish(self):
        if not self.file.closed:
            raise RuntimeError("Cannot publish an unfinished upload")
        # Same-directory hard link publishes atomically without replacing existing data.
        os.link(self.temp_path, self.path)
        self.published = True

    def keep(self):
        self.committed = True

    def close(self):
        try:
            self.file.close()
        finally:
            try:
                self.temp_path.unlink(missing_ok=True)
            finally:
                if self.published and not self.committed:
                    self.path.unlink(missing_ok=True)


class MaterialStorage:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, user_id, space_id, asset_id):
        if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", key) for key in (user_id, space_id, asset_id)):
            raise ProviderError("invalid_storage_key", "无效的文件存储标识", 422)
        path = self.root / user_id / space_id / (asset_id + ".bin")
        if not path.resolve().is_relative_to(self.root):
            raise ProviderError("invalid_storage_key", "文件存储路径不可访问", 422)
        return path

    @contextmanager
    def stage(self, user_id, space_id, asset_id, filename, mime, max_bytes):
        validator = PDFStreamValidator(filename, mime, max_bytes)
        staged = StagedMaterial(self.path(user_id, space_id, asset_id), validator)
        try:
            yield staged
        finally:
            staged.close()

    def save(self, user_id, space_id, asset_id, data):
        path = self.path(user_id, space_id, asset_id)
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        return str(path)

    def open(self, user_id, space_id, asset_id):
        try:
            return self.path(user_id, space_id, asset_id).open("rb")
        except OSError:
            raise ProviderError("file_unavailable", "原始文件不可用，请重新上传", 422) from None

    def read(self, user_id, space_id, asset_id):
        with self.open(user_id, space_id, asset_id) as file:
            return file.read()

    def delete(self, user_id, space_id, asset_id):
        self.path(user_id, space_id, asset_id).unlink(missing_ok=True)

    def delete_space(self, user_id, space_id):
        directory = self.path(user_id, space_id, "space-delete").parent
        if directory.exists():
            # Also erase staging files left by an interrupted local upload.
            shutil.rmtree(directory)

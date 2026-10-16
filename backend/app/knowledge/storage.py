import os
import re
from pathlib import Path

from app.providers.base import ProviderError


def validate_pdf(filename, mime, data, max_bytes):
    if len(data) > max_bytes:
        raise ProviderError("file_too_large", "文件超过本服务的上传大小限制", 413)
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
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        raise ProviderError("invalid_file", "文件格式标识与 PDF 不符或文件不完整", 422)
    # Conservative byte signature checks only; no document body extraction/OCR.
    if any(
        signature in data
        for signature in (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/OpenAction", b"/RichMedia")
    ):
        raise ProviderError("unsafe_file", "文件包含主动内容或嵌入内容标识，请提供不含这些内容的 PDF", 422)


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

    def save(self, user_id, space_id, asset_id, data):
        path = self.path(user_id, space_id, asset_id)
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
        return str(path)

    def read(self, user_id, space_id, asset_id):
        try:
            return self.path(user_id, space_id, asset_id).read_bytes()
        except OSError:
            raise ProviderError("file_unavailable", "原始文件不可用，请重新上传", 422) from None

    def delete(self, user_id, space_id, asset_id):
        self.path(user_id, space_id, asset_id).unlink(missing_ok=True)

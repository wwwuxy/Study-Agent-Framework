"""Bounded format validation; never extracts student text or performs OCR."""

import io
import shutil
import warnings
from pathlib import Path

from PIL import Image

from app.knowledge.storage import MaterialStorage, PDFStreamValidator, StagedMaterial
from app.providers.base import ProviderError


class ImageValidator:
    def __init__(self, filename, mime, max_bytes):
        suffix = ".png" if mime == "image/png" else (".jpg", ".jpeg")
        if not filename.lower().endswith(suffix):
            raise ProviderError("unsupported_file_type", "图片文件名与格式不一致", 422)
        self.mime = mime
        self.base = PDFStreamValidator("placeholder.pdf", "application/pdf", max_bytes)
        self.buffer = io.BytesIO()

    @property
    def size_bytes(self):
        return self.base.size_bytes

    @property
    def hash(self):
        return self.base.hash

    def update(self, chunk):
        self.base.size_bytes += len(chunk)
        if self.size_bytes > self.base.max_bytes:
            raise ProviderError("file_too_large", "图片超过上传大小限制", 413)
        self.base.hash.update(chunk)
        self.buffer.write(chunk)

    def finish(self):
        try:
            self.buffer.seek(0)
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(self.buffer) as image:
                    if image.format != ("PNG" if self.mime == "image/png" else "JPEG"):
                        raise ValueError()
                    w, h = image.size
                    if not 0 < w <= 8192 or not 0 < h <= 8192 or w * h > 32_000_000:
                        raise ValueError()
                    if getattr(image, "n_frames", 1) != 1:
                        raise ValueError()
                    image.verify()
        except (
            OSError,
            ValueError,
            SyntaxError,
            Image.DecompressionBombWarning,
            Image.DecompressionBombError,
        ):
            raise ProviderError("invalid_image", "图片损坏、格式不符或像素超过限制", 422) from None
        finally:
            self.buffer.close()


class ExamStorage(MaterialStorage):
    def __init__(self, root):
        super().__init__(Path(root) / "exams")

    def stage(self, user_id, space_id, attachment_id, manifest, max_bytes):
        from contextlib import contextmanager

        name = manifest.filename
        if "/" in name or "\\" in name or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ProviderError("invalid_filename", "文件名不合法", 422)
        validator = (
            PDFStreamValidator(name, manifest.mime_type, max_bytes)
            if manifest.mime_type == "application/pdf"
            else ImageValidator(name, manifest.mime_type, max_bytes)
        )

        @contextmanager
        def staged_file():
            staged = StagedMaterial(self.path(user_id, space_id, attachment_id), validator)
            try:
                yield staged
            finally:
                staged.close()

        return staged_file()

    def discard_space(self, user_id, space_id):
        path = self.path(user_id, space_id, "space").parent
        if path.exists():
            shutil.rmtree(path)

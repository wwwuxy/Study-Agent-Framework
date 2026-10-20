"""Framework-generated visual random markers, never user-document parsing."""

import base64
import io

from PIL import Image, ImageDraw, ImageFont


def make_probe_image(marker, mime):
    image = Image.new("RGB", (900, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 50), marker, fill="black", font=ImageFont.load_default(size=44))
    stream = io.BytesIO()
    image.save(stream, format="PNG" if mime == "image/png" else "JPEG", quality=95)
    return "data:" + mime + ";base64," + base64.b64encode(stream.getvalue()).decode()
